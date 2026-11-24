from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StagedTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    occurred_at: date
    amount: Decimal
    currency: str
    direction: Literal["inflow", "outflow"]
    merchant_raw: str
    merchant_clean: str
    description: str | None
    suggested_category_id: UUID | None
    confidence: Decimal
    categorization_source: str
    is_duplicate: bool
    needs_review: bool
    user_approved: bool


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    account_id: UUID
    langgraph_thread_id: str
    filename: str
    doc_type: str
    status: str
    total_rows: int
    duplicate_rows: int
    needs_review_rows: int
    committed_rows: int
    balance_reconciled: bool | None
    reconciliation_note: str | None
    error_message: str | None
    created_at: datetime


class ImportBatchDetailResponse(ImportBatchResponse):
    staged_transactions: list[StagedTransactionResponse]


class StagedTransactionDecision(BaseModel):
    staged_id: UUID
    user_approved: bool = True
    merchant_clean: str | None = Field(default=None, max_length=160)
    category_id: UUID | None = None
    direction: Literal["inflow", "outflow"] | None = None
    amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    occurred_at: date | None = None
    description: str | None = None


class ImportReviewCommitRequest(BaseModel):
    decisions: list[StagedTransactionDecision] = Field(default_factory=list)
    skip_duplicates: bool = True
    learn_from_edits: bool = True


class DeleteImportBatchResponse(BaseModel):
    deleted_batch_id: UUID
    deleted_transactions: int
    recalculated_account_id: UUID | None = None
    new_account_balance: Decimal | None = None
