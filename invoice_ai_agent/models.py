from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal

class LineItem(BaseModel):
    description: str = Field(description="Item description in Japanese")
    quantity: Optional[int] = Field(default=None, description="Quantity, null if lump sum")
    unit: str = Field(description="Unit (e.g., 個, 式, 箱)")
    unit_price: Optional[int] = Field(default=None, description="Unit price, null if lump sum")
    amount: int = Field(description="Total amount for this line. MUST be negative if preceded by △ or minus.")
    tax_code: Literal["T10", "T08"] = Field(description="T10 (10%) or T08 (8% for food/beverage)")

class ExtractedInvoice(BaseModel):
    invoice_number: str
    issue_date_raw: str
    due_date_raw: str
    partner_name: str
    lines: List[LineItem]
    confidence_score: int = Field(ge=0, le=100, description="Confidence 0-100 based on OCR clarity")
    anomalies: List[str] = Field(default_factory=list, description="e.g., 'Handwritten date override detected'")

class ProcessingResult(BaseModel):
    status: Literal["SUCCESS", "MANUAL_REVIEW", "FAILED"]
    invoice_number: str
    partner_code: Optional[str]
    payload: Optional[dict] = None
    error_message: Optional[str] = None
    agent_notes: str