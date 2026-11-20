from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AccountType = Literal["checking", "savings", "credit", "cash", "investment", "loan"]


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: AccountType
    currency: str = Field(default="USD", min_length=3, max_length=3)
    initial_balance: Decimal = Field(default=Decimal("0.00"))
    institution: str | None = Field(default=None, max_length=120)
    color: str = Field(default="#10b981", max_length=16)


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: AccountType | None = None
    institution: str | None = Field(default=None, max_length=120)
    color: str | None = Field(default=None, max_length=16)
    is_archived: bool | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    type: AccountType
    currency: str
    initial_balance: Decimal
    current_balance: Decimal
    institution: str | None
    color: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
