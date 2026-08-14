from pydantic import BaseModel, ConfigDict, Field


class PayeeCategoryRuleCreate(BaseModel):
    category_id: int
    contains_text: str = Field(min_length=1, max_length=255)
    sort_order: int = 0


class PayeeCategoryRuleUpdate(BaseModel):
    category_id: int | None = None
    contains_text: str | None = Field(default=None, min_length=1, max_length=255)
    sort_order: int | None = None


class PayeeCategoryRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    contains_text: str
    sort_order: int
