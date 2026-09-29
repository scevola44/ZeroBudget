from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.schemas.reset import ResetRequest, ResetResponse
from app.services.data_reset import reset_data

router = APIRouter(prefix="/api/reset", tags=["reset"])


@router.post("", response_model=ResetResponse)
async def reset(body: ResetRequest, db: DbSession, current_user: CurrentUser) -> ResetResponse:
    return await reset_data(db, current_user.id, body.options)
