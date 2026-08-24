import base64
import fitz
from openai import AsyncOpenAI
import instructor
from typing import List, Dict, Any
from models import ExtractedInvoice, LineItem
from config import settings
from utils.logger import logger

class DynamicInvoiceExtractor:
    def __init__(self):
        self.client = instructor.from_openai(
            AsyncOpenAI(api_key=settings.openai_api_key),
            mode=instructor.Mode.JSON
        )
    
    def _analyze_document_quality(self, images_b64: List[str]) -> Dict[str, Any]:
        """Dynamically assess document quality to adjust extraction strategy."""
        quality_indicators = {
            'is_scanned': False,
            'has_handwriting': False,
            'is_multi_page': len(images_b64) > 1,
            'page_count': len(images_b64),
            'complexity': 'low'
        }
        
        # Analyze first page for quality indicators
        if images_b64:
            # Simple heuristic: if we have many images, likely complex
            if len(images_b64) > 1:
                quality_indicators['complexity'] = 'high'
            elif len(images_b64) == 1:
                quality_indicators['complexity'] = 'medium'
        
        return quality_indicators
    
    def _build_adaptive_prompt(self, doc_quality: Dict[str, Any]) -> str:
        """Build extraction prompt adapted to document characteristics."""
        base_prompt = """You are an expert Japanese invoice OCR and data extraction AI.
Extract the data into the requested JSON schema with maximum accuracy."""
        
        # Adapt based on document quality
        if doc_quality['has_handwriting']:
            base_prompt += "\n\n⚠️ WARNING: This document contains handwritten text. Pay extra attention to date overrides and manual annotations."
        
        if doc_quality['is_multi_page']:
            base_prompt += f"\n\n📄 This is a {doc_quality['page_count']}-page document. You MUST extract line items from ALL pages and aggregate them."
        
        if doc_quality['complexity'] == 'high':
            base_prompt += "\n\n🔍 This is a complex document with many line items. Be meticulous in extracting each line."
        
        base_prompt += """
        
EXTRACTION RULES:
1. **Dates**: Extract EXACTLY as written (e.g., '2026年1月7日', '令和8年2月5日', '2026/01/18'). Do not convert.
2. **Amounts**: If you see △ (triangle) or - (minus) indicating discount/debit, output as NEGATIVE integer (e.g., -30000).
3. **Nulls**: If quantity or unit_price is not present (lump sum fees), set them to null.
4. **Tax Codes**: 
   - T08 (8%): Food/beverage items (食品, コーヒー, 水, 飲料, 冷凍食材)
   - T10 (10%): Everything else
5. **Confidence Scoring**:
   - 90-100: Perfect text layer, clear layout
   - 70-89: Good quality, minor ambiguities
   - 50-69: Scanned/blurry, some uncertainty
   - <50: Poor quality, significant doubts
6. **Anomalies**: Note ANY handwritten changes, stamps, corrections, or unusual markings.

Return ONLY valid JSON matching the schema."""
        
        return base_prompt
    
    async def extract(self, file_path: str) -> ExtractedInvoice:
        """Extract invoice data with adaptive strategies."""
        # Convert PDF/images to base64
        images_b64 = []
        doc = fitz.open(file_path)
        
        for page_num, page in enumerate(doc):
            pix = page.get_pixmap(dpi=settings.dpi_for_ocr)
            images_b64.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
        
        # Analyze document quality
        doc_quality = self._analyze_document_quality(images_b64)
        
        # Build adaptive prompt
        prompt = self._build_adaptive_prompt(doc_quality)
        
        # Prepare content for GPT-4o
        content = [{"type": "text", "text": prompt}]
        
        for img_b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"}
            })
        
        # Extract with retry logic
        for attempt in range(settings.max_retries):
            try:
                result = await self.client.chat.completions.create(
                    model=settings.llm_model,
                    response_model=ExtractedInvoice,
                    messages=[{"role": "user", "content": content}],
                    temperature=settings.llm_temperature,
                    timeout=settings.request_timeout
                )
                
                # Add document quality metadata
                result.metadata = {
                    'doc_quality': doc_quality,
                    'extraction_attempt': attempt + 1
                }
                
                return result
                
            except Exception as e:
                if attempt == settings.max_retries - 1:
                    raise Exception(f"Extraction failed after {settings.max_retries} attempts: {str(e)}")
                logger.logger.warning(f"Extraction attempt {attempt + 1} failed, retrying...")