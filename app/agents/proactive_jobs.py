"""ProactiveJobsAgent tanımı."""

from functools import lru_cache

from pydantic_ai import Agent

from app.agents.deps import AgentDeps
from app.llm.provider import get_llm_model_string
from app.models.domain import ProactiveRunSummary
from app.tools.email import prepare_supplier_email
from app.tools.messaging import (
    send_owner_email_draft,
    send_owner_summary,
    send_proactive_message,
)
from app.tools.shipments import list_shipments_anomaly
from app.tools.stock import list_low_stock


@lru_cache(maxsize=1)
def get_proactive_jobs_agent() -> Agent:
    """
    ProactiveJobsAgent'ı lazy şekilde oluşturur.

    Agent import anında değil, gerçekten çalıştırılacağı zaman oluşturulur.
    Böylece GOOGLE_API_KEY yokken basit import/syntax testleri patlamaz.
    """

    return Agent(
        model=get_llm_model_string(),
        deps_type=AgentDeps,
        output_type=ProactiveRunSummary,
        tools=[
            list_shipments_anomaly,
            list_low_stock,
            send_proactive_message,
            send_owner_summary,
            prepare_supplier_email,
            send_owner_email_draft,
        ],
        system_prompt=(
            "You are ProactiveJobsAgent for a small business operations demo. "
            "Your job is to detect cargo anomalies and low-stock risks. "
            "For cargo anomalies, send a proactive customer message using "
            "send_proactive_message. The messaging tool already handles 24-hour "
            "idempotency, so do not try to bypass it. "
            "For low stock, send a static owner summary using send_owner_summary, "
            "then prepare supplier email drafts and send them to the owner for "
            "approval with send_owner_email_draft. Never claim an email was sent to "
            "a supplier directly; only drafts are sent to the owner for approval. "
            "At the end, return a ProactiveRunSummary with accurate counts."
        ),
    )


async def run_proactive_jobs(deps: AgentDeps) -> ProactiveRunSummary:
    """
    Proaktif operasyon kontrolünü manuel olarak çalıştırır.

    Args:
        deps: DB session, Telegram ve ayar bilgilerini taşıyan AgentDeps.

    Returns:
        ProactiveRunSummary çıktısı.
    """

    agent = get_proactive_jobs_agent()

    result = await agent.run(
        (
            "Run the proactive operations check now. "
            "Check shipment anomalies and low-stock items. "
            "Use the available tools to take the correct proactive actions. "
            "Return an accurate ProactiveRunSummary."
        ),
        deps=deps,
    )

    return result.output
