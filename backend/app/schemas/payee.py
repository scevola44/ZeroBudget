from pydantic import BaseModel, ConfigDict, Field


class PayeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PayeeUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class PayeeMergeRequest(BaseModel):
    source_id: int
    target_id: int


class PayeeMergeResponse(BaseModel):
    merged_count: int
