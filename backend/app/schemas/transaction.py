from datetime import date as DateType

from pydantic import BaseModel, ConfigDict, Field


class TransactionSplitInput(BaseModel):
    category_id: int | None = None
    amount_cents: int
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
    is_ready_to_assign: bool = False
    date: DateType
    payee: str = Field(default="", max_length=255)
    memo: str = Field(default="", max_length=500)
    amount_cents: int  # signed: positive = inflow, negative = outflow
    splits: list[TransactionSplitInput] = Field(default_factory=list)


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    is_ready_to_assign: bool | None = None
    date: DateType | None = None
    payee: str | None = Field(default=None, max_length=255)
    memo: str | None = Field(default=None, max_length=500)
    amount_cents: int | None = None
    # None = leave splits unchanged. [] = clear splits, reverting to a plain
    # category. Non-empty = replace wholesale (delete + recreate — split
    # counts are small, so diffing buys nothing).
    splits: list[TransactionSplitInput] | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    category_id: int | None
    is_ready_to_assign: bool
    date: DateType
    payee: str
    payee_id: int | None = None
    memo: str
    amount_cents: int
    transfer_peer_id: int | None = None
    # The account holding the other leg. Denormalized onto the response so a
    # transaction list can label transfers without fetching the peer rows.
    transfer_peer_account_id: int | None = None
    splits: list[TransactionSplitResponse] = Field(default_factory=list)


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


class PayeeTransferSuggestion(BaseModel):
    # A transaction whose payee names another of the user's accounts, and that
    # account has no bank connection — so nothing was ever going to sync the
    # other leg for suggest_pairs to find.
    transaction: TransactionResponse
    to_account_id: int
    to_account_name: str


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


class UnassignedCountResponse(BaseModel):
    count: int


class BulkDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class BulkDeleteResponse(BaseModel):
    deleted: int


class BulkSetCategoryRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    # None clears to unassigned.
    category_id: int | None = None


class BulkSetCategoryResponse(BaseModel):
    updated: int


class TransactionPage(BaseModel):
    items: list[TransactionResponse]
    # Present when more rows exist past this page; pass back as ``cursor`` to
    # fetch the next one. None when this page reached the end (or the caller
    # never asked for pagination via ``limit``).
    next_cursor: str | None = None
