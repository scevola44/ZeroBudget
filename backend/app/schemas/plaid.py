from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LinkTokenResponse(BaseModel):
    link_token: str


class ExchangeRequest(BaseModel):
    public_token: str = Field(min_length=1)


class SkippedAccount(BaseModel):
    plaid_account_id: str
    name: str
    reason: str


class PlaidItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution_name: str | None
    last_synced_at: datetime | None
    last_error_code: str | None


class ExchangeResponse(BaseModel):
    item: PlaidItemResponse
    account_ids: list[int]
    skipped_accounts: list[SkippedAccount]
    sync: "SyncResponse"


class SyncResponse(BaseModel):
    added: int
    modified: int
    removed: int
    skipped_pending: int
    skipped_non_eur: int
    skipped_unknown_account: int
    last_synced_at: datetime | None
    error_code: str | None = None
    touched_account_ids: list[int]


ExchangeResponse.model_rebuild()
