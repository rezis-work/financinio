from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TransactionDirection = Literal["inflow", "outflow"]


class TransactionCreate(BaseModel):
    account_id: UUID
    category_id: UUID | None = None
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fx_rate: Decimal = Field(default=Decimal("1.000000"), gt=Decimal("0"))
    direction: TransactionDirection
    occurred_at: date
    merchant: str = Field(min_length=1, max_length=160)
    description: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_transfer: bool = False
    transfer_account_id: UUID | None = None


class TransactionUpdate(BaseModel):
    account_id: UUID | None = None
    category_id: UUID | None = None
    amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    direction: TransactionDirection | None = None
    occurred_at: date | None = None
    merchant_clean: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    is_transfer: bool | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    category_id: UUID | None
    amount: Decimal
    currency: str
    base_amount: Decimal
    fx_rate: Decimal
    direction: TransactionDirection
    occurred_at: date
    merchant_raw: str
    merchant_clean: str
    description: str | None
    notes: str | None
    tags: list[str]
    is_transfer: bool
    transfer_peer_id: UUID | None
    source_document_id: UUID | None
    ai_confidence: Decimal | None
    created_at: datetime


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    limit: int
    offset: int


class BulkCategorizeRequest(BaseModel):
    transaction_ids: list[UUID] = Field(min_length=1)
    category_id: UUID | None
    learn_memory: bool = True
