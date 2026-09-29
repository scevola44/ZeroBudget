from enum import StrEnum

from pydantic import BaseModel, Field


class ResetOption(StrEnum):
    TRANSACTIONS = "transactions"
    ASSIGNMENTS = "assignments"


class ResetRequest(BaseModel):
    options: list[ResetOption] = Field(min_length=1)


class ResetResponse(BaseModel):
    deleted_transactions: int = 0
    deleted_assignments: int = 0
