from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.base import ResponseModel


class ResetOption(StrEnum):
    TRANSACTIONS = "transactions"
    ASSIGNMENTS = "assignments"


class ResetRequest(BaseModel):
    options: list[ResetOption] = Field(min_length=1)


class ResetResponse(ResponseModel):
    deleted_transactions: int = 0
    deleted_assignments: int = 0
