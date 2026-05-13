from app.security.pii import redact, restore, PIIMap

def test_pii_t1_tc():
    # PII-T1
    text = "TC kimliğim 12345678901"
    redacted, pii_map = redact(text)
    assert redacted == "TC kimliğim [TC_REDACTED_0]"
    assert pii_map.entries == {"[TC_REDACTED_0]": "12345678901"}
    assert restore(redacted, pii_map) == text

def test_pii_t2_phone():
    # PII-T2
    text = "telefon: 0532 123 45 67"
    redacted, pii_map = redact(text)
    assert redacted == "telefon: [TEL_REDACTED_0]"
    assert pii_map.entries == {"[TEL_REDACTED_0]": "0532 123 45 67"}
    assert restore(redacted, pii_map) == text

def test_pii_t3_multiple_phones():
    # PII-T3
    text = "+90 532 111 22 33 veya 0212 555 66 77"
    redacted, pii_map = redact(text)
    assert "[TEL_REDACTED_0]" in redacted
    assert "[TEL_REDACTED_1]" in redacted
    assert len(pii_map.entries) == 2
    assert restore(redacted, pii_map) == text

def test_pii_t4_iban():
    # PII-T4
    text = "IBAN: TR33 0006 1005 1978 6457 8413 26"
    redacted, pii_map = redact(text)
    assert redacted == "IBAN: [IBAN_REDACTED_0]"
    assert pii_map.entries == {"[IBAN_REDACTED_0]": "TR33 0006 1005 1978 6457 8413 26"}
    assert restore(redacted, pii_map) == text

def test_pii_t5_card():
    # PII-T5
    text = "kartım: 4111 1111 1111 1111"
    redacted, pii_map = redact(text)
    assert redacted == "kartım: [KART_REDACTED_0]"
    assert pii_map.entries == {"[KART_REDACTED_0]": "4111 1111 1111 1111"}
    assert restore(redacted, pii_map) == text

def test_pii_t6_no_pii():
    # PII-T6
    text = "sipariş 1024 ne durumda?"
    redacted, pii_map = redact(text)
    assert redacted == text
    assert pii_map.entries == {}
    assert restore(redacted, pii_map) == text

def test_pii_t7_email():
    # PII-T7
    text = "e-posta: test@ornek.com"
    redacted, pii_map = redact(text)
    assert redacted == "e-posta: [EPOSTA_REDACTED_0]"
    assert pii_map.entries == {"[EPOSTA_REDACTED_0]": "test@ornek.com"}
    assert restore(redacted, pii_map) == text

def test_pii_t8_mixed():
    # PII-T8
    text = "TC: 12345678901, tel: 0532 123 45 67"
    redacted, pii_map = redact(text)
    assert "[TC_REDACTED_0]" in redacted
    assert "[TEL_REDACTED_0]" in redacted
    assert len(pii_map.entries) == 2
    assert restore(redacted, pii_map) == text

def test_pii_t9_invalid_tc_starts_with_zero():
    # PII-T9: 0 ile başlayan 11 haneli sayı TC kabul edilmemeli.
    # Ancak telefon formatına (0 ile başlayan 11 haneli) uyduğu için TEL olarak maskelenir.
    text = "01234567890"
    redacted, pii_map = redact(text)
    assert "[TC_REDACTED_0]" not in redacted
    assert "[TEL_REDACTED_0]" in redacted
    assert pii_map.entries == {"[TEL_REDACTED_0]": "01234567890"}
    assert restore(redacted, pii_map) == text
