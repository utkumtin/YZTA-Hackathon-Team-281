"""app/agents/router.py — Kanal bazlı agent dispatch (rule-based, LLM'siz)."""

from enum import StrEnum


class AgentTarget(StrEnum):
    CUSTOMER_SUPPORT = "customer_support"
    PROACTIVE_JOBS = "proactive_jobs"


def route(source: str) -> AgentTarget:
    """Gelen kaynağa göre agent hedefini belirler.

    source = 'telegram_webhook' → CustomerSupportAgent
    source = 'scheduled_jobs'   → ProactiveJobsAgent
    """
    if source == "scheduled_jobs":
        return AgentTarget.PROACTIVE_JOBS
    return AgentTarget.CUSTOMER_SUPPORT
