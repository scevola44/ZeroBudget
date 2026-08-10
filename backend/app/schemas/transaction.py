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
    transfer_peer_id: int | None = None
    # The account holding the other leg. Denormalized onto the response so a
    # transaction list can label transfers without fetching the peer rows.
    transfer_peer_account_id: int | None = None


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    date: DateType
    payee: str = Field(default="", max_length=255)
    memo: str = Field(default="", max_length=500)
    # Magnitude only — each leg derives its own sign from the direction.
    amount_cents: int = Field(gt=0)


class TransferResponse(BaseModel):
    from_transaction: TransactionResponse
    to_transaction: TransactionResponse


class TransactionImportRow(BaseModel):
    account_id: int
    category_id: int | None = None
    date: DateType
    payee: str = Field(default="", max_length=255)
    memo: str = Field(default="", max_length=500)
    amount_cents: int


class TransactionImportRequest(BaseModel):
    rows: list[TransactionImportRow]


class TransactionImportResponse(BaseModel):
    imported: int
