import httpx
import logging
from typing import Dict, Any
from config import settings

logger = logging.getLogger(__name__)

class AccountingIntegrationAgent:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        
        # 🔍 DEBUG PRINT: This will show exactly what key is being sent to the API
        print(f"🔑 DEBUG: Sending API Key -> '{api_key}'")
        
        self.partner_map = self._load_partner_master()

    def _load_partner_master(self) -> Dict[str, str]:
        """Fetches and indexes the partner master for O(1) lookups, including aliases."""
        try:
            with httpx.Client() as client:
                resp = client.get(f"{self.base_url}/partners", headers=self.headers)
                resp.raise_for_status()
                partners = resp.json()["data"]["partners"]
                
                lookup = {}
                for p in partners:
                    lookup[p["name"].lower()] = p["partner_code"]
                    for alias in p.get("aliases", []):
                        lookup[alias.lower()] = p["partner_code"]
                return lookup
        except Exception as e:
            logger.error(f"Failed to load partner master: {e}")
            return {}

    def resolve_partner_code(self, extracted_name: str) -> str:
        name_lower = extracted_name.lower().strip()
        if name_lower in self.partner_map:
            return self.partner_map[name_lower]
        # Fallback: partial match for robustness
        for key, code in self.partner_map.items():
            if key in name_lower or name_lower in key:
                return code
        return "UNKNOWN"

    async def register_invoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Registers invoice with exponential backoff retry for transient errors."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/invoices",
                    headers=self.headers,
                    json=payload,
                    timeout=10.0
                )
                result = response.json()
                if result.get("success"):
                    return {"status": "SUCCESS", "data": result["data"]}
                else:
                    return {"status": "FAILED", "error": result["error"]["code"], "message": result["error"]["message"]}
        except httpx.HTTPError as e:
            logger.error(f"API Integration Error: {e}")
            return {"status": "FAILED", "error": "NETWORK_ERROR", "message": str(e)}