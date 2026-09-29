"""User-triggered wipes of budget data, one handler per selectable option.

Handlers never commit; the caller applies the chosen options in a single
transaction so a failure part-way leaves everything untouched.
"""

from collections.abc import Awaitable, Callable

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BankConnection, DeletedExternalTransaction, MonthlyAssignment, Transaction
from app.schemas.reset import ResetOption, ResetResponse


async def reset_transactions(db: AsyncSession, user_id: int) -> ResetResponse:
    """Delete every transaction and make the next sync re-align linked accounts.

    Tombstones are cleared too: they would otherwise make the sync skip both the
    re-import and the "opening_balance" entry that re-aligns to the real balance.
    Clearing ``last_synced_at`` is what makes the sync run its first-sync path,
    the only place that opening-balance entry is created.
    """
    deleted = await db.execute(delete(Transaction).where(Transaction.user_id == user_id))
    await db.execute(
        delete(DeletedExternalTransaction).where(DeletedExternalTransaction.user_id == user_id)
    )
    await db.execute(
        update(BankConnection).where(BankConnection.user_id == user_id).values(last_synced_at=None)
    )
    return ResetResponse(deleted_transactions=deleted.rowcount)


async def reset_assignments(db: AsyncSession, user_id: int) -> ResetResponse:
    deleted = await db.execute(delete(MonthlyAssignment).where(MonthlyAssignment.user_id == user_id))
    return ResetResponse(deleted_assignments=deleted.rowcount)


RESET_HANDLERS: dict[ResetOption, Callable[[AsyncSession, int], Awaitable[ResetResponse]]] = {
    ResetOption.TRANSACTIONS: reset_transactions,
    ResetOption.ASSIGNMENTS: reset_assignments,
}


async def reset_data(
    db: AsyncSession, user_id: int, options: list[ResetOption]
) -> ResetResponse:
    combined = ResetResponse()
    for option in set(options):
        result = await RESET_HANDLERS[option](db, user_id)
        combined.deleted_transactions += result.deleted_transactions
        combined.deleted_assignments += result.deleted_assignments
    await db.commit()
    return combined
