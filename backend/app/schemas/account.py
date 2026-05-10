from pydantic import BaseModel, ConfigDict, Field

from app.models.scope import PERSONAL, Scope


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(default="checking", max_length=32)
    scope: Scope = PERSONAL


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: str | None = Field(default=None, max_length=32)
    scope: Scope | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    scope: Scope
    balance_cents: int = 0
    # Plaid metadata (all None for manual accounts).
    plaid_item_id: int | None = None
    plaid_mask: str | None = None
    institution_name: str | None = None
