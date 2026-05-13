"""
app/llm/provider.py — LLMProvider abstraction

Agent'lar model string'i doğrudan hardcode etmez; bu fonksiyonu çağırır.
"""

from app.config import settings


def get_llm_model_string() -> str:
    """
    Agent'ların kullandığı PydanticAI model string'ini config'den üretir.

    Not:
        PydanticAI, Gemini için provider adını "gemini" olarak değil,
        Google AI Studio için "google-gla" olarak bekler.

    Örnek:
        LLM_PROVIDER=gemini
        LLM_MODEL=gemini-2.5-flash

        dönüş:
        google-gla:gemini-2.5-flash
    """

    provider = (settings.llm_provider or "gemini").strip().lower()
    model = (settings.llm_model or "gemini-2.5-flash").strip()

    # Eğer kullanıcı .env içine direkt tam PydanticAI model string'i yazarsa,
    # örn: LLM_MODEL=google-gla:gemini-2.5-flash
    # onu bozmadan döndür.
    if ":" in model:
        return model

    if provider in {"gemini", "google", "google-gla", "google_ai", "google-ai"}:
        return f"google-gla:{model}"

    if provider in {"openai", "chatgpt"}:
        return f"openai:{model}"

    # Diğer provider'lar için kullanıcı PydanticAI'ın beklediği provider adını vermişse kullan.
    return f"{provider}:{model}"
