"""One-off backfill for ``transfer_match_candidates`` after migration 0015.

The table is maintained incrementally from here on (see
``services/transfer_candidate_store.py``), but transactions that existed
before this deploy never went through that write path, so their candidate
pairs are missing until this runs once.

Idempotent and safe to re-run: it just calls the same
``sync_candidates_for`` every write chokepoint calls, once per currently
linkable transaction. Usage::

    python -m scripts.backfill_transfer_match_candidates
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Transaction
from app.services.transfer_candidate_store import sync_candidates_for


async def backfill() -> None:
    async with SessionLocal() as db:
        result = await db.execute(
            select(Transaction.id, Transaction.user_id).where(
                Transaction.transfer_peer_id.is_(None)
            )
        )
        rows = result.all()
        for index, (transaction_id, user_id) in enumerate(rows, start=1):
            await sync_candidates_for(db, user_id, transaction_id)
            if index % 500 == 0:
                await db.commit()
                print(f"backfilled {index}/{len(rows)} transactions")
        await db.commit()
        print(f"done: backfilled {len(rows)} transactions")


if __name__ == "__main__":
    asyncio.run(backfill())
