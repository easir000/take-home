import re

def normalize_japanese_date(raw_date: str) -> str:
    """Converts Japanese business dates to strict YYYY-MM-DD format."""
    # 1. Safely handle None or non-string values
    if not raw_date or not isinstance(raw_date, str):
        return "2026-01-01"  # Safe fallback date
        
    raw = raw_date.strip()
    
    # 2. Handle Imperial Era: 令和 (Reiwa) 8年 = 2026
    reiwa_match = re.search(r'令和(\d{1,2})年(\d{1,2})月(\d{1,2})日', raw)
    if reiwa_match:
        return f"{2018 + int(reiwa_match.group(1))}-{int(reiwa_match.group(2)):02d}-{int(reiwa_match.group(3)):02d}"
    
    # 3. Handle Standard Kanji: 2026年1月7日
    kanji_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', raw)
    if kanji_match:
        return f"{kanji_match.group(1)}-{int(kanji_match.group(2)):02d}-{int(kanji_match.group(3)):02d}"
    
    # 4. Handle Slashes or Hyphens: 2026/01/18 or 2026-01-18
    slash_match = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', raw)
    if slash_match:
        return f"{slash_match.group(1)}-{int(slash_match.group(2)):02d}-{int(slash_match.group(3)):02d}"
    
    # 5. Fallback: return the original string (the API will catch it if it's invalid)
    return raw