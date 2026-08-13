from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AspspResponse(BaseModel):
    name: str
    country: str
    logo: str | None = None


class ConnectRequest(BaseModel):
    aspsp_name: str = Field(min_length=1, max_length=255)
    aspsp_country: str = Field(min_length=2, max_length=2)
    scope_id: int


class ConnectResponse(BaseModel):
    authorization_url: str
    state: str


class CallbackRequest(BaseModel):
    code: str = Field(min_length=1)
    state: str = Field(min_length=1)


class SkippedAccount(BaseModel):
    name: str
    reason: str


class BankConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    aspsp_name: str
    aspsp_country: str
    valid_until: datetime | None
    last_synced_at: datetime | None
    last_error_code: str | None


class ConnectionSyncResult(BaseModel):
    connection_id: int
    aspsp_name: str
    added: int
    modified: int
    skipped_pending: int
    skipped_non_eur: int
    skipped_unknown_account: int
    skipped_unparseable_date: int
    skipped_deleted: int
    error_code: str | None = None
    touched_account_ids: list[int]


class SyncStatusResponse(BaseModel):
    mode: str
    max_per_day: int
    used_today: int
    remaining_today: int
    last_run_at: datetime | None
    # Only set in auto mode: when the scheduler will next consider a run.
    next_auto_sync_at: datetime | None


class GlobalSyncResponse(BaseModel):
    status: str
    connections: list[ConnectionSyncResult]
    quota: SyncStatusResponse


class CallbackResponse(BaseModel):
    connection: BankConnectionResponse
    account_ids: list[int]
    skipped_accounts: list[SkippedAccount]
    sync: ConnectionSyncResult
