from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # API Configuration
    api_base_url: str = "http://localhost:8080"
    api_key: str = "demo-key-1234"
    use_mock_ai: bool = False  # Set to True in .env if OpenAI quota is exceeded
    
    # LLM Configuration
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.1
    max_retries: int = 3
    request_timeout: int = 30
    
    # Processing Configuration
    confidence_threshold: float = 75.0
    dpi_for_ocr: int = 150
    enable_human_review: bool = True
    batch_size: int = 5
    
    # Tax Configuration
    tax_rates: dict = {"T10": 0.10, "T08": 0.08}
    # FIX: Provide a default list directly instead of None
    food_keywords: List[str] = [
        '食品', '食材', 'コーヒー', '水', '飲料', '冷凍', 
        '米', '野菜', '肉', '魚', 'トイレットペーパー',
        '清涼飲料', 'ジュース', 'ビール', 'ワイン'
    ]
    
    # Logging
    log_level: str = "INFO"
    enable_detailed_logging: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()