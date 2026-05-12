import re
from typing import Dict, Tuple
from pydantic import BaseModel, Field

class PIIMap(BaseModel):
    entries: Dict[str, str] = Field(default_factory=dict)

# Regex Patterns
# TC Kimlik: 11 haneli sayı
TC_PATTERN = re.compile(r'\b\d{11}\b')

# Telefon Numarası: opsiyonel +90 veya 0, opsiyonel parantez, boşluklu/tireli veya bitişik numaralar
# Örn: 0532 123 45 67, +90 532 111 22 33, 0212 555 66 77
PHONE_PATTERN = re.compile(r'(?:\+?90|0)?[\s\-]*\(?\d{3}\)?[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}')

# IBAN: TR ile başlar, 2 hane, sonra 4'erli veya bitişik haneler
IBAN_PATTERN = re.compile(r'\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b')

# Kredi Kartı: 16 hane, opsiyonel boşluk veya tire
CARD_PATTERN = re.compile(r'\b\d{4}(?:[\s\-]?\d{4}){3}\b')

# E-Posta
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

def redact(text: str) -> Tuple[str, PIIMap]:
    """
    Metin içindeki PII (TC, Telefon, IBAN, Kart, E-posta) verilerini bulup maskeler.
    Bulunan her orijinal veriyi pii_map içine saklar.
    """
    pii_map = PIIMap()
    
    # Sıra önemlidir, IBAN içinde TC gibi rakam dizileri olabilir, ancak
    # TR prefix'i IBAN'ı ayırt eder.
    
    # Her bir PII türü için index sayaçları
    counters = {
        "IBAN": 0,
        "TC": 0,
        "KART": 0,
        "TEL": 0,
        "EPOSTA": 0
    }
    
    def replacer(match: re.Match, ptype: str) -> str:
        original_val = match.group(0)
        idx = counters[ptype]
        counters[ptype] += 1
        placeholder = f"[{ptype}_REDACTED_{idx}]"
        pii_map.entries[placeholder] = original_val
        return placeholder

    # 1. Email
    text = EMAIL_PATTERN.sub(lambda m: replacer(m, "EPOSTA"), text)
    # 2. IBAN
    text = IBAN_PATTERN.sub(lambda m: replacer(m, "IBAN"), text)
    # 3. Kredi Kartı
    text = CARD_PATTERN.sub(lambda m: replacer(m, "KART"), text)
    # 4. TC
    text = TC_PATTERN.sub(lambda m: replacer(m, "TC"), text)
    # 5. Telefon
    text = PHONE_PATTERN.sub(lambda m: replacer(m, "TEL"), text)

    return text, pii_map

def restore(text: str, pii_map: PIIMap) -> str:
    """
    Maskelenmiş metindeki placeholder'ları orijinal verilerle değiştirir.
    """
    restored_text = text
    for placeholder, original_val in pii_map.entries.items():
        restored_text = restored_text.replace(placeholder, original_val)
    return restored_text
