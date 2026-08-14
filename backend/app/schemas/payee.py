from pydantic import BaseModel, ConfigDict, Field


class PayeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PayeeRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class PayeeMergeRequest(BaseModel):
    source_ids: list[int] = Field(min_length=1)


class PayeeMergeResponse(BaseModel):
    reassigned: int
