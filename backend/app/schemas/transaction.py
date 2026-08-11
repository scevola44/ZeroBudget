from datetime import date as DateType

from pydantic import BaseModel, ConfigDict, Field


class TransactionSplitInput(BaseModel):
    category_id: int | None = None
    amount_cents: int  # signed; every line's amount must sum to the parent amount
    memo: str = Field(default="", max_length=500)


class TransactionSplitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    amount_cents: int
    memo: str


class TransactionCreate(BaseModel):
    account_id: int
    category_id: int | None = None
    date: DateType
    payee: str = Field(default="", max_length=255)
    memo: str = Field(default="", max_length=500)
    amount_cents: int  # signed: positive = inflow, negative = outflow
    # Two or more lines to split this transaction across categories. When
    # given, category_id above must be omitted/null — the parent stays
    # uncategorized and activity is attributed per line (see txn_rows.py).
    splits: list[TransactionSplitInput] | None = None


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    date: DateType | None = None
    payee: str | None = Field(default=None, max_length=255)
    memo: str | None = Field(default=None, max_length=500)
    amount_cents: int | None = None
    # Omitted: leave existing splits untouched. []: clear them, reverting to
    # a plain transaction. Non-empty: replace them entirely.
    splits: list[TransactionSplitInput] | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    category_id: int | None
    date: DateType
    payee: str
    # Denormalized: the resolved Payee row backing the string above, or None
    # for a blank/synthetic payee. See Transaction.payee_id's TODO.
    payee_id: int | None = None
    memo: str
    amount_cents: int
    transfer_peer_id: int | None = None
    # The account holding the other leg. Denormalized onto the response so a
    # transaction list can label transfers without fetching the peer rows.
    transfer_peer_account_id: int | None = None
    splits: list[TransactionSplitResponse] = []


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


class TransferLinkRequest(BaseModel):
    # Exactly one of these: link to a row that already exists, or create the
    # missing leg in an account that has nothing to link to (see link_transfer).
    peer_transaction_id: int | None = None
    to_account_id: int | None = None


class TransferCandidate(BaseModel):
    transaction: TransactionResponse
    # Signed, relative to the transaction being linked: -2 means the candidate
    # is dated two days earlier. Lets the picker say "2 days before" without
    # re-deriving it from two dates.
    date_offset_days: int


class TransferSuggestion(BaseModel):
    outflow: TransactionResponse
    inflow: TransactionResponse


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


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int


class BulkCategoryRequest(BaseModel):
    transaction_ids: list[int]
    category_id: int | None = None


class BulkCategoryResponse(BaseModel):
    updated: int


class BulkDeleteRequest(BaseModel):
    transaction_ids: list[int]


class BulkDeleteResponse(BaseModel):
    deleted: int
