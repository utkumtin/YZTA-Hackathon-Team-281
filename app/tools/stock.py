"""Stok tarama tool'ları."""

from pydantic_ai import RunContext
from sqlalchemy import select

from app.agents.deps import AgentDeps
from app.models.domain import LowStockItem
from app.models.tables import Product, Stock, Supplier


async def list_low_stock(
    ctx: RunContext[AgentDeps],
    limit: int = 20,
) -> list[LowStockItem]:
    """
    Find products whose stock quantity is at or below the reorder threshold.

    Args:
        ctx: Runtime context containing AgentDeps and the async database session.
        limit: Maximum number of low-stock items to return.

    Returns:
        A list of LowStockItem objects with sku, product name, current quantity,
        threshold, supplier email and supplier name.

    Use this tool before preparing supplier email drafts or owner summaries.

    Concurrency note:
        PydanticAI may execute multiple tools concurrently. SQLAlchemy AsyncSession
        does not allow concurrent operations on the same session, so the DB query is
        guarded with ctx.deps.db_lock.
    """

    db = ctx.deps.db

    stmt = (
        select(Stock, Product, Supplier)
        .join(Product, Product.sku == Stock.sku)
        .join(Supplier, Supplier.id == Product.supplier_id)
        .where(Stock.current_qty <= Stock.threshold)
        .order_by(Stock.current_qty.asc())
        .limit(limit)
    )

    async with ctx.deps.db_lock:
        rows = (await db.execute(stmt)).all()

    return [
        LowStockItem(
            sku=stock.sku,
            name=product.name,
            current_qty=stock.current_qty,
            threshold=stock.threshold,
            supplier_email=supplier.email,
            supplier_name=supplier.name,
        )
        for stock, product, supplier in rows
    ]
