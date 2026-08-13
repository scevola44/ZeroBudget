from pydantic import BaseModel, ConfigDict, Field

from app.models.scope import SCOPE_NAME_MAX_LENGTH


class ScopeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=SCOPE_NAME_MAX_LENGTH)


class ScopeUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=SCOPE_NAME_MAX_LENGTH)


class ScopeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int
