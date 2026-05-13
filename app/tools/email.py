"""Supplier email drafting tool."""

from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from sqlalchemy import select
from functools import lru_cache

from app.agents.deps import AgentDeps
from app.llm.provider import get_llm_model_string
from app.models.domain import SupplierEmailDraft
from app.models.tables import Product, Supplier


@lru_cache(maxsize=1)
def build_supplier_email_agent() -> Agent:
    """
    Builds the supplier email sub-agent lazily.

    The agent is created only when prepare_supplier_email is called.
    This prevents import-time failures when GOOGLE_API_KEY is not available
    during simple syntax/import checks.
    """

    return Agent(
        model=get_llm_model_string(),
        deps_type=AgentDeps,
        output_type=SupplierEmailDraft,
        output_retries=2,
        system_prompt=(
            "You prepare concise, professional supplier email drafts. "
            "Return only structured output matching the SupplierEmailDraft schema. "
            "The email should be polite, specific, and suitable for a purchasing workflow."
        ),
    )


async def prepare_supplier_email(
    ctx: RunContext[AgentDeps],
    sku: str,
    suggested_qty: int,
) -> SupplierEmailDraft:
    """
    Prepare a structured supplier replenishment email draft for a low-stock SKU.

    This tool uses a dedicated PydanticAI sub-agent. The sub-agent is configured
    with ``output_retries=2`` so that transient structured-output / JSON parsing
    failures can be retried during demo runs.

    Args:
        ctx: Runtime context containing AgentDeps and the async database session.
        sku: Low-stock product SKU.
        suggested_qty: Quantity to request from the supplier.

    Returns:
        SupplierEmailDraft with subject, body, to_email, sku and suggested_qty.

    Concurrency note:
        PydanticAI may execute multiple tools concurrently. SQLAlchemy AsyncSession
        does not allow concurrent operations on the same session, so the DB query is
        guarded with ctx.deps.db_lock. The LLM call is intentionally outside the DB lock.
    """

    db = ctx.deps.db

    stmt = (
        select(Product, Supplier)
        .join(Supplier, Supplier.id == Product.supplier_id)
        .where(Product.sku == sku)
    )

    async with ctx.deps.db_lock:
        row = (await db.execute(stmt)).first()

    if not row:
        raise ValueError(f"Product not found for sku={sku}")

    product, supplier = row

    prompt = f"""
Create a supplier replenishment email draft.

Product SKU: {product.sku}
Product name: {product.name}
Product description: {product.description or '-'}
Supplier name: {supplier.name}
Supplier email: {supplier.email}
Suggested order quantity: {suggested_qty}

Rules:
- Write in Turkish.
- Be polite and concise.
- Ask whether the supplier can provide the requested quantity.
- Ask for estimated delivery date.
- Ask for price confirmation.
- Use to_email={supplier.email}, sku={product.sku}, suggested_qty={suggested_qty}.
"""

    supplier_email_agent = build_supplier_email_agent()

    try:
        result = await supplier_email_agent.run(prompt, deps=ctx.deps)
        draft = result.output

        subject = draft.subject
        body = draft.body

    except ModelHTTPError:
        subject = f"{product.sku} - Stok Yenileme Talebi"
        body = (
            f"Merhaba {supplier.name},\n\n"
            f"{product.sku} kodlu {product.name} ürünü için "
            f"{suggested_qty} adet tedarik talebimiz bulunmaktadır.\n\n"
            "Bu miktarı sağlayıp sağlayamayacağınızı, güncel birim fiyat bilgisini "
            "ve tahmini teslim tarihini bizimle paylaşabilir misiniz?\n\n"
            "Teşekkürler."
        )

    # Guardrail: DB'den gelen kritik alanları LLM çıktısına karşı override et.
    return SupplierEmailDraft(
        subject=subject,
        body=body,
        to_email=supplier.email,
        sku=product.sku,
        suggested_qty=suggested_qty,
    )
