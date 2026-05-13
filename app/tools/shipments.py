"""Kargo anomaly tarama tool'ları."""

from datetime import datetime, timedelta, timezone

from pydantic_ai import RunContext
from sqlalchemy import select

from app.agents.deps import AgentDeps
from app.models.domain import ActiveShipmentInfo, Carrier, ShipmentAnomaly, ShipmentStatus
from app.models.tables import Order, Shipment


async def list_shipments_anomaly(
    ctx: RunContext[AgentDeps],
    older_than_hours: int = 6,
    limit: int = 20,
) -> list[ShipmentAnomaly]:
    """
    Find shipments that may require proactive customer communication.

    A shipment is considered anomalous when its status is ``in_transit`` and its
    last status update is older than ``older_than_hours``. The tool returns only
    non-PII operational fields so the agent can decide whether to inform the
    customer without seeing customer name, phone, address, or email.

    Args:
        ctx: Runtime context containing AgentDeps and the async database session.
        older_than_hours: Minimum age of the last shipment update in hours.
        limit: Maximum number of anomaly records to return.

    Returns:
        A list of ShipmentAnomaly objects containing order_id, customer_id,
        tracking_id, carrier, current_branch and waited_hours.

    Concurrency note:
        PydanticAI may execute multiple tools concurrently. SQLAlchemy AsyncSession
        does not allow concurrent operations on the same session, so the DB query is
        guarded with ctx.deps.db_lock.
    """

    db = ctx.deps.db
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=older_than_hours)

    stmt = (
        select(Shipment, Order)
        .join(Order, Order.id == Shipment.order_id)
        .where(
            Shipment.status == "in_transit",
            Shipment.last_status_change_at <= cutoff,
        )
        .order_by(Shipment.last_status_change_at.asc())
        .limit(limit)
    )

    async with ctx.deps.db_lock:
        rows = (await db.execute(stmt)).all()

    anomalies: list[ShipmentAnomaly] = []

    for shipment, order in rows:
        waited_hours = int(
            (now - shipment.last_status_change_at).total_seconds() // 3600)

        anomalies.append(
            ShipmentAnomaly(
                order_id=order.id,
                customer_id=order.customer_id,
                tracking_id=shipment.tracking_id,
                carrier=Carrier(shipment.carrier),
                current_branch=shipment.current_branch,
                waited_hours=waited_hours,
            )
        )

    return anomalies


async def list_active_shipments(
    ctx: RunContext[AgentDeps],
    limit: int = 50,
) -> list[ActiveShipmentInfo]:
    """
    Fetch all active shipments for the morning briefing.

    A shipment is considered active when its status is not ``delivered`` or
    ``returned``. The ``is_delayed`` flag is set when the last status update is
    older than 24 hours, which lets the briefing report count delayed shipments
    without an additional query.

    Args:
        ctx: Runtime context containing AgentDeps and the async database session.
        limit: Maximum number of records to return.

    Returns:
        A list of ActiveShipmentInfo objects. Does not contain PII.

    Concurrency note:
        DB query is guarded with ctx.deps.db_lock because PydanticAI may run
        tools concurrently on the same AsyncSession.
    """

    db = ctx.deps.db
    now = datetime.now(timezone.utc)
    delay_cutoff = now - timedelta(hours=24)

    stmt = (
        select(Shipment)
        .where(Shipment.status.notin_(["delivered", "returned"]))
        .order_by(Shipment.last_status_change_at.asc())
        .limit(limit)
    )

    async with ctx.deps.db_lock:
        rows = (await db.execute(stmt)).scalars().all()

    return [
        ActiveShipmentInfo(
            tracking_id=shipment.tracking_id,
            carrier=Carrier(shipment.carrier),
            status=ShipmentStatus(shipment.status),
            current_branch=shipment.current_branch,
            eta=shipment.eta,
            is_delayed=shipment.last_status_change_at <= delay_cutoff,
        )
        for shipment in rows
    ]
