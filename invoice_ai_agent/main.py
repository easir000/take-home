import asyncio
import os
import json
import math
import base64
from datetime import datetime
from typing import List, Dict

import pymupdf as fitz  # Modern import to fix deprecation warning
from dotenv import load_dotenv
from openai import AsyncOpenAI
import instructor
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.console import Console

from config import settings
from models import ExtractedInvoice, ProcessingResult, LineItem
from utils.date_parser import normalize_japanese_date
from agents.integration_agent import AccountingIntegrationAgent

# 1. Load environment variables at the very top
load_dotenv()

console = Console()

class DynamicInvoiceProcessor:
    def __init__(self):
        # 2. Hardcoded fallbacks to guarantee the script runs even if .env is misconfigured
        openai_api_key = os.getenv("OPENAI_API_KEY", "sk-fallback-key")
        api_base_url = os.getenv("API_BASE_URL", "http://localhost:8080")
        mock_api_key = os.getenv("API_KEY", "demo-key-1234")
        
        console.print(f"⚙️ Loaded API Base URL: {api_base_url}")
        console.print(f"🔑 Loaded Mock API Key: '{mock_api_key}'")

        self.llm = instructor.from_openai(
            AsyncOpenAI(api_key=openai_api_key),
            mode=instructor.Mode.JSON
        )
        
        self.integration = AccountingIntegrationAgent(
            base_url=api_base_url, 
            api_key=mock_api_key
        )
        self.results = []

    async def process_single_invoice(self, file_path: str, index: int, total: int) -> Dict:
        """Process a single invoice with full error handling and routing logic."""
        filename = os.path.basename(file_path)
        result = {
            'filename': filename,
            'invoice_number': None,
            'status': 'PENDING',
            'timestamp': datetime.now().isoformat(),
            'processing_time': None
        }
        
        start_time = datetime.now()
        
        try:
            console.print(f"\n[cyan]⏳ Processing [{index}/{total}]: {filename}[/cyan]")
            
            # Step 1: AI Extraction (or Mock Fallback)
            extracted = await self._extract(file_path)
            result['invoice_number'] = extracted.invoice_number
            
            console.print(f"   [green]✓ Extracted:[/green] {extracted.invoice_number} | Confidence: {extracted.confidence_score}%")
            
            # Step 2: Intelligent Validation & Enrichment
            enriched = self._verify_and_enrich(extracted)
            
            # Step 3: Partner Resolution
            partner_code = self.integration.resolve_partner_code(enriched['partner_name'])
            enriched['partner_code'] = partner_code
            
            # Step 4: Routing Logic (Human-in-the-Loop for edge cases)
            if partner_code == "UNKNOWN":
                result['status'] = 'MANUAL_REVIEW'
                result['error_message'] = 'PARTNER_NOT_FOUND: New supplier requires onboarding'
                result['agent_notes'] = f"Supplier '{enriched['partner_name']}' not in master"
                console.print(f"   [yellow]⚠️ MANUAL REVIEW:[/yellow] {result['error_message']}")
                
            elif enriched['confidence'] < settings.confidence_threshold:
                result['status'] = 'MANUAL_REVIEW'
                result['error_message'] = f"LOW_CONFIDENCE: {enriched['confidence']}% < {settings.confidence_threshold}%"
                result['agent_notes'] = f"Confidence too low: {enriched['confidence']}%"
                console.print(f"   [yellow]⚠️ MANUAL REVIEW:[/yellow] {result['error_message']}")
                
            elif len(enriched['anomalies']) > 0:
                result['status'] = 'MANUAL_REVIEW'
                result['error_message'] = f"ANOMALIES_DETECTED: {', '.join(enriched['anomalies'])}"
                result['agent_notes'] = f"Anomalies: {enriched['anomalies']}"
                console.print(f"   [yellow]⚠️ MANUAL REVIEW:[/yellow] {result['error_message']}")
                
            else:
                # Step 5: API Submission
                api_result = await self.integration.register_invoice(enriched)
                
                if api_result['status'] == 'SUCCESS':
                    result['status'] = 'SUCCESS'
                    result['payload'] = enriched
                    result['agent_notes'] = 'Auto-processed successfully'
                    console.print(f"   [green]✅ SUCCESS:[/green] Registered with API")
                else:
                    result['status'] = 'FAILED'
                    result['error_message'] = f"{api_result.get('error', 'UNKNOWN')}: {api_result.get('message', '')}"
                    result['agent_notes'] = f"API rejection: {api_result.get('error')}"
                    console.print(f"   [red]❌ FAILED:[/red] {result['error_message']}")
        
        except Exception as e:
            result['status'] = 'FAILED'
            result['error_message'] = f"Processing error: {str(e)}"
            result['agent_notes'] = 'Critical error during processing'
            console.print(f"   [red]❌ CRITICAL ERROR:[/red] {str(e)}")
        
        finally:
            end_time = datetime.now()
            result['processing_time'] = (end_time - start_time).total_seconds()
            self.results.append(result)
        
        return result

    async def _extract(self, file_path: str) -> ExtractedInvoice:
        """AI OCR Agent: Converts document to structured data."""
        filename = os.path.basename(file_path)
        
        # 🛡️ FALLBACK: If OpenAI quota is exceeded, use mock data to keep pipeline running
        if settings.use_mock_ai:
            console.print(f"   [yellow]⚠️ Using Mock AI Extraction (OpenAI Quota Exceeded)[/yellow]")
            return self._get_mock_extraction(filename)

        # Standard GPT-4o Vision Extraction
        images_b64 = []
        doc = fitz.open(file_path)
        for page in doc:
            pix = page.get_pixmap(dpi=settings.dpi_for_ocr)
            images_b64.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))

        content = [{"type": "text", "text": """
            Extract Japanese invoice data strictly into the JSON schema.
            RULES: 
            1. Dates: Extract exactly as written (e.g., '令和8年', '2026/01/18').
            2. Amounts: Treat '△' or '-' as negative integers (e.g., -30000).
            3. Tax: Assign 'T08' to food/beverage (食品, コーヒー, 水), 'T10' to all else.
            4. Confidence: Rate 0-100. Deduct points for handwritten overrides or blur.
            5. Anomalies: Note any handwritten changes (e.g., 'Due date changed by hand').
        """}]
        for img in images_b64:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}})

        return await self.llm.chat.completions.create(
            model=settings.llm_model, response_model=ExtractedInvoice, messages=[{"role": "user", "content": content}]
        )

    def _get_mock_extraction(self, filename: str) -> ExtractedInvoice:
        """Provides realistic mock extraction data to prove the pipeline works without LLM."""
        mock_data = {
            "invoice_01.pdf": ExtractedInvoice(
                invoice_number="YM-2026-0107", issue_date_raw="2026年1月7日", due_date_raw="2026年2月28日",
                partner_name="株式会社山田製作所", confidence_score=95, anomalies=[],
                lines=[
                    LineItem(description="精密部品A-100", quantity=120, unit="個", unit_price=1250, amount=150000, tax_code="T10"),
                    LineItem(description="精密部品B-220", quantity=40, unit="個", unit_price=3400, amount=136000, tax_code="T10"),
                    LineItem(description="梱包・輸送費", quantity=None, unit="式", unit_price=None, amount=18000, tax_code="T10")
                ]
            ),
            "invoice_02.pdf": ExtractedInvoice(
                invoice_number="OSK-26-0112", issue_date_raw="2026年1月12日", due_date_raw="2026年2月20日",
                partner_name="大阪機械工業株式会社", confidence_score=92, anomalies=["Multi-page document aggregated"],
                lines=[
                    LineItem(description="治具部材 No.001", quantity=6, unit="個", unit_price=930, amount=5580, tax_code="T10"),
                    LineItem(description="治具部材 No.026", quantity=31, unit="個", unit_price=4180, amount=129580, tax_code="T10")
                ]
            ),
            "invoice_03.pdf": ExtractedInvoice(
                invoice_number="TF-2026-0115", issue_date_raw="2026年1月15日", due_date_raw="2026年2月15日",
                partner_name="東京フーズ株式会社", confidence_score=90, anomalies=[],
                lines=[
                    LineItem(description="業務用コーヒー豆 1kg", quantity=24, unit="袋", unit_price=2800, amount=67200, tax_code="T08"),
                    LineItem(description="紙コップ 100個入", quantity=30, unit="箱", unit_price=1200, amount=36000, tax_code="T10"),
                    LineItem(description="配送手数料", quantity=None, unit="式", unit_price=None, amount=3500, tax_code="T10")
                ]
            ),
            "invoice_09.pdf": ExtractedInvoice(
                invoice_number="OSK-26-0128", issue_date_raw="2026年1月28日", due_date_raw="2026年2月20日",
                partner_name="大阪機械工業株式会社", confidence_score=85, anomalies=["Scanned PDF, slight skew"],
                lines=[
                    LineItem(description="沙节7卜加工", quantity=37, unit="個", unit_price=2733, amount=101121, tax_code="T10"),
                    LineItem(description="熱处理", quantity=37, unit="個", unit_price=891, amount=32967, tax_code="T10")
                ]
            )
        }
        
        # Default fallback for any other invoice file (e.g., invoice_04.jpg, etc.)
        return mock_data.get(filename, ExtractedInvoice(
            invoice_number="MOCK-000", issue_date_raw="2026/01/01", due_date_raw="2026/01/31",
            partner_name="株式会社山田製作所", confidence_score=80, anomalies=["Mock data used due to quota limit"],
            lines=[LineItem(description="Mock Service", quantity=1, unit="式", unit_price=10000, amount=10000, tax_code="T10")]
        ))

    def _verify_and_enrich(self, extracted: ExtractedInvoice) -> dict:
        """Validator Agent: Deterministic math verification and business rule enforcement."""
        # Recalculate totals (The API will reject if these don't match exactly)
        subtotal = sum(line.amount for line in extracted.lines)
        t10_sub = sum(line.amount for line in extracted.lines if line.tax_code == "T10")
        t08_sub = sum(line.amount for line in extracted.lines if line.tax_code == "T08")
        tax = math.floor(t10_sub * 0.10) + math.floor(t08_sub * 0.08)
        total = subtotal + tax

        # Normalize dates to YYYY-MM-DD
        issue_date = normalize_japanese_date(extracted.issue_date_raw)
        due_date = normalize_japanese_date(extracted.due_date_raw)

        return {
            'partner_name': extracted.partner_name,
            'invoice_number': extracted.invoice_number,
            'issue_date': issue_date,
            'due_date': due_date,
            'currency': 'JPY',
            'lines': [line.model_dump() for line in extracted.lines],
            'subtotal': subtotal,
            'tax_amount': tax,
            'total_amount': total,
            'confidence': extracted.confidence_score,
            'anomalies': extracted.anomalies
        }

    async def process_batch(self, invoice_dir: str = "invoices"):
        """Process all invoices with progress tracking."""
        files = [
            os.path.join(invoice_dir, f) 
            for f in sorted(os.listdir(invoice_dir))
            if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png'))
        ]
        
        if not files:
            console.print(f"[red]No invoice files found in {invoice_dir}[/red]")
            return
        
        console.print(f"\n[bold blue]🚀 Starting AI Agent Invoice Processing Pipeline...[/bold blue]")
        console.print(f"Total files to process: {len(files)}\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            processing_task = progress.add_task("[cyan]Processing invoices...", total=len(files))
            for idx, file_path in enumerate(files, 1):
                await self.process_single_invoice(file_path, idx, len(files))
                progress.update(processing_task, advance=1)
        
        # Save detailed report
        self._save_report()

    def _save_report(self):
        """Save detailed processing report."""
        report = {
            'processing_timestamp': datetime.now().isoformat(),
            'configuration': {
                'model': settings.llm_model,
                'confidence_threshold': settings.confidence_threshold,
                'use_mock_ai': settings.use_mock_ai,
                'total_processed': len(self.results)
            },
            'results': self.results,
            'summary': {
                'success': sum(1 for r in self.results if r['status'] == 'SUCCESS'),
                'manual_review': sum(1 for r in self.results if r['status'] == 'MANUAL_REVIEW'),
                'failed': sum(1 for r in self.results if r['status'] == 'FAILED'),
            }
        }
        
        with open('processing_report.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        console.print(f"\n[bold green]✓ Detailed report saved to processing_report.json[/bold green]")

async def main():
    processor = DynamicInvoiceProcessor()
    await processor.process_batch("invoices")

if __name__ == "__main__":
    asyncio.run(main())