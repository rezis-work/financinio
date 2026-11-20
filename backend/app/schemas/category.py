from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CategoryKind = Literal["income", "expense", "transfer"]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: CategoryKind = "expense"
    icon: str = Field(default="tag", max_length=32)
    color: str = Field(default="#6366f1", max_length=16)
    parent_id: UUID | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: CategoryKind | None = None
    icon: str | None = Field(default=None, max_length=32)
    color: str | None = Field(default=None, max_length=16)
    parent_id: UUID | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    kind: CategoryKind
    icon: str
    color: str
    parent_id: UUID | None
    is_system: bool


class RuleCreate(BaseModel):
    match_pattern: str = Field(min_length=1, max_length=200)
    match_type: Literal["contains", "exact", "regex"] = "contains"
    category_id: UUID
    merchant_override: str | None = Field(default=None, max_length=160)
    priority: int = Field(default=100, ge=1, le=1000)


class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    match_pattern: str
    match_type: str
    category_id: UUID
    merchant_override: str | None
    priority: int
    is_active: bool
