import logging
import sys
from datetime import datetime
from typing import Optional
from rich.logging import RichHandler
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from config import settings

console = Console()

class InvoiceProcessingLogger:
    def __init__(self, name: str = "InvoiceAI"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, settings.log_level.upper()))
        
        # Rich handler for beautiful console output
        handler = RichHandler(
            rich_tracebacks=True,
            tracebacks_show_locals=settings.enable_detailed_logging,
            markup=True
        )
        handler.setFormatter(logging.Formatter(
            '%(message)s',
            datefmt='[%X]'
        ))
        self.logger.addHandler(handler)
        
    def log_processing_start(self, total_files: int):
        console.print(Panel(
            f"[bold blue]Starting Invoice Processing Pipeline[/bold blue]\n"
            f"Total files to process: {total_files}\n"
            f"Model: {settings.llm_model}\n"
            f"Confidence Threshold: {settings.confidence_threshold}%",
            title="🚀 Invoice AI Agent",
            border_style="blue"
        ))
    
    def log_invoice_processing(self, filename: str, index: int, total: int):
        self.logger.info(f"[bold cyan]Processing[/bold cyan] [{index}/{total}] {filename}")
    
    def log_extraction_success(self, invoice_number: str, confidence: int):
        confidence_color = "green" if confidence >= 80 else "yellow" if confidence >= 60 else "red"
        console.print(f"  ✓ Extracted: [bold]{invoice_number}[/bold] | Confidence: [{confidence_color}]{confidence}%[/{confidence_color}]")
    
    def log_verification_result(self, status: str, details: str):
        icon = "✅" if status == "PASS" else "⚠️" if status == "WARNING" else "❌"
        color = "green" if status == "PASS" else "yellow" if status == "WARNING" else "red"
        console.print(f"  {icon} Verification [{color}]{status}[/{color}]: {details}")
    
    def log_api_submission(self, status: str, message: str):
        icon = "" if status == "SUCCESS" else "️" if status == "REVIEW" else "❌"
        color = "green" if status == "SUCCESS" else "yellow" if status == "REVIEW" else "red"
        console.print(f"  {icon} API Result: [{color}]{status}[/{color}] - {message}")
    
    def log_error(self, filename: str, error: str):
        console.print(f"  ❌ [bold red]Error[/bold red] processing {filename}: {error}")
    
    def display_summary(self, results: list):
        total = len(results)
        success = sum(1 for r in results if r['status'] == 'SUCCESS')
        review = sum(1 for r in results if r['status'] == 'MANUAL_REVIEW')
        failed = sum(1 for r in results if r['status'] == 'FAILED')
        
        table = Table(title="📊 Processing Summary", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Percentage", justify="right")
        
        table.add_row("Total Processed", str(total), "100%")
        table.add_row("✅ Success", f"[green]{success}[/green]", f"{(success/total)*100:.1f}%")
        table.add_row("⚠️ Manual Review", f"[yellow]{review}[/yellow]", f"{(review/total)*100:.1f}%")
        table.add_row("❌ Failed", f"[red]{failed}[/red]", f"{(failed/total)*100:.1f}%")
        
        console.print(table)
        
        # Display failed/review items
        if review > 0 or failed > 0:
            review_table = Table(title=" Items Requiring Attention", show_header=True)
            review_table.add_column("Status", style="cyan")
            review_table.add_column("Invoice", style="yellow")
            review_table.add_column("Reason", style="white")
            
            for r in results:
                if r['status'] in ['MANUAL_REVIEW', 'FAILED']:
                    review_table.add_row(
                        f"[{'yellow' if r['status'] == 'MANUAL_REVIEW' else 'red'}]{r['status']}[/{'yellow' if r['status'] == 'MANUAL_REVIEW' else 'red'}]",
                        r.get('invoice_number', 'Unknown'),
                        r.get('error_message', r.get('agent_notes', 'N/A'))[:50]
                    )
            console.print(review_table)

logger = InvoiceProcessingLogger()