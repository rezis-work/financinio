from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class UploadedDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "uploaded_documents"
    __table_args__ = (Index("ix_uploaded_docs_user_sha", "user_id", "sha256"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # csv | xlsx | pdf_statement | receipt
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_batches"
    __table_args__ = (Index("ix_import_batches_user_created", "user_id", "created_at"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("uploaded_documents.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    langgraph_thread_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="processing", nullable=False
    )  # processing | needs_review | committed | failed
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    needs_review_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    committed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    balance_reconciled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reconciliation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    document = relationship("UploadedDocument")
    staged_transactions = relationship(
        "StagedTransaction", back_populates="batch", cascade="all, delete-orphan"
    )


class StagedTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staged_transactions"
    __table_args__ = (Index("ix_staged_tx_batch", "batch_id"),)

    batch_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # inflow | outflow
    merchant_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_clean: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_category_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.500"), nullable=False
    )
    categorization_source: Mapped[str] = mapped_column(
        String(16), default="llm", nullable=False
    )  # rule | vector | llm | heuristic | manual
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    batch = relationship("ImportBatch", back_populates="staged_transactions")
    suggested_category = relationship("Category")
