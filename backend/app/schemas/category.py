from pydantic import BaseModel, ConfigDict, Field


class CategoryGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class CategoryGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = None


class CategoryCreate(BaseModel):
    group_id: int
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    group_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    name: str
    sort_order: int


class CategoryGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int
    categories: list[CategoryResponse] = []
