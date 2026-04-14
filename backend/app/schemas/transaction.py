from datetime import date as DateType

from pydantic import BaseModel, ConfigDict, Field


class TransactionCreate(BaseModel):
    account_id: int
    category_id: int | None = None
    date: DateType
    payee: str = Field(default="", max_length=255)
    memo: str = Field(default="", max_length=500)
    amount_cents: int  # signed: positive = inflow, negative = outflow


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    date: DateType | None = None
    payee: str | None = Field(default=None, max_length=255)
    memo: str | None = Field(default=None, max_length=500)
    amount_cents: int | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    category_id: int | None
    date: DateType
    payee: str
    memo: str
    amount_cents: int
