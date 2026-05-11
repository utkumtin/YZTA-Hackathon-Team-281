"""
app/llm/provider.py — LLMProvider abstraction

Agent'lar model string'i doğrudan hardcode etmez; bu fonksiyonu çağırır.
"""

from app.config import settings


def get_llm_model_string() -> str:
    """Agent'ların kullandığı model string'ini config'den toplar.

    Dönüş formatı PydanticAI convention'ına uyar:
    ``"{provider}:{model}"``  →  örn. ``"gemini:gemini-2.5-flash"``

    Agent kurulumu:
        agent = Agent(model=get_llm_model_string(), ...)
    """
    return f"{settings.llm_provider}:{settings.llm_model}"
