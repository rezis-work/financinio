import base64
import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.checkpointer import checkpointer_manager
from app.ai.graphs.ingestion_graph import build_ingestion_graph
from app.ai.observability import build_langgraph_config
from app.api.deps import get_current_user, get_storage_dep, get_vector_dep
from app.core.database import get_db
from app.core.storage import StorageBackend
from app.models.finance import Account, CategorizationRule, Category, Transaction
from app.models.ingestion import ImportBatch, StagedTransaction, UploadedDocument
from app.models.user import User
from app.schemas.ingestion import (
    ImportBatchDetailResponse,
    ImportBatchResponse,
    ImportReviewCommitRequest,
    StagedTransactionResponse,
)
from app.services.ledger_service import compute_transaction_fingerprint, recalculate_account_balance
from app.services.quota_service import (
    TokenMeterCallbackHandler,
    enforce_ai_quota,
    record_ai_usage,
)
from app.services.vector_service import VectorMemoryBackend

router = APIRouter(prefix="/imports", tags=["AI Document Ingestion"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB


def _detect_doc_type(
    filename: str, mime_type: str
) -> Literal["csv", "xlsx", "pdf_statement", "receipt"]:
    ext = Path(filename).suffix.lower()
    if ext == ".csv" or mime_type in ("text/csv", "application/csv"):
        return "csv"
    if ext in (".xlsx", ".xls") or "spreadsheetml" in mime_type:
        return "xlsx"
    if ext == ".pdf" or mime_type == "application/pdf":
        return "pdf_statement"
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".heic") or mime_type.startswith("image/"):
        return "receipt"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported file format. Upload CSV, Excel (.xlsx), PDF statement, or receipt image.",
    )


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        chunks.append(clean[start : start + chunk_size])
        start += chunk_size - overlap
    return chunks


def _batch_to_response(batch: ImportBatch) -> ImportBatchResponse:
    return ImportBatchResponse(
        id=batch.id,
        document_id=batch.document_id,
        account_id=batch.account_id,
        langgraph_thread_id=batch.langgraph_thread_id,
        filename=batch.document.filename if batch.document else "upload",
        doc_type=batch.document.doc_type if batch.document else "csv",
        status=batch.status,
        total_rows=batch.total_rows,
        duplicate_rows=batch.duplicate_rows,
        needs_review_rows=batch.needs_review_rows,
        committed_rows=batch.committed_rows,
        balance_reconciled=batch.balance_reconciled,
        reconciliation_note=batch.reconciliation_note,
        error_message=batch.error_message,
        created_at=batch.created_at,
    )


@router.get("", response_model=list[ImportBatchResponse])
async def list_import_batches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImportBatchResponse]:
    batches = (
        await db.scalars(
            select(ImportBatch)
            .options(selectinload(ImportBatch.document))
            .where(ImportBatch.user_id == current_user.id)
            .order_by(ImportBatch.created_at.desc())
            .limit(30)
        )
    ).all()
    return [_batch_to_response(b) for b in batches]


@router.get("/{batch_id}", response_model=ImportBatchDetailResponse)
async def get_import_batch(
    batch_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportBatchDetailResponse:
    batch = await db.scalar(
        select(ImportBatch)
        .options(selectinload(ImportBatch.document), selectinload(ImportBatch.staged_transactions))
        .where(ImportBatch.id == batch_id, ImportBatch.user_id == current_user.id)
    )
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found.")

    base = _batch_to_response(batch)
    staged_sorted = sorted(
        batch.staged_transactions,
        key=lambda s: int((s.raw_payload or {}).get("__row_index", 0)),
    )
    return ImportBatchDetailResponse(
        **base.model_dump(),
        staged_transactions=[StagedTransactionResponse.model_validate(s) for s in staged_sorted],
    )


@router.post("/upload", response_model=ImportBatchDetailResponse, status_code=status.HTTP_201_CREATED)
async def upload_and_parse_document(
    account_id: UUID = Form(...),
    doc_type_override: Literal["csv", "xlsx", "pdf_statement", "receipt"] | None = Form(default=None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> ImportBatchDetailResponse:
    account = await db.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target account not found.")

    enforce_ai_quota(current_user)

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 15 MB limit.",
        )

    filename = file.filename or "statement.csv"
    mime_type = file.content_type or "application/octet-stream"
    doc_type = doc_type_override or _detect_doc_type(filename, mime_type)

    storage_key = await storage.save(current_user.id, filename, raw_bytes)
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    document = UploadedDocument(
        user_id=current_user.id,
        account_id=account.id,
        filename=filename,
        mime_type=mime_type,
        file_size=len(raw_bytes),
        storage_key=storage_key,
        doc_type=doc_type,
        sha256=sha256,
    )
    db.add(document)
    await db.flush()

    thread_id = f"import-{uuid4().hex}"
    batch = ImportBatch(
        user_id=current_user.id,
        document_id=document.id,
        account_id=account.id,
        langgraph_thread_id=thread_id,
        status="processing",
    )
    db.add(batch)
    await db.flush()

    # Load user context for the LangGraph ingestion pipeline
    categories = (
        await db.scalars(select(Category).where(Category.user_id == current_user.id))
    ).all()
    rules = (
        await db.scalars(
            select(CategorizationRule)
            .where(
                CategorizationRule.user_id == current_user.id,
                CategorizationRule.is_active.is_(True),
            )
            .order_by(CategorizationRule.priority.asc())
        )
    ).all()
    existing_fps = (
        await db.scalars(
            select(Transaction.fingerprint).where(
                Transaction.user_id == current_user.id,
                Transaction.account_id == account.id,
            )
        )
    ).all()

    graph = build_ingestion_graph(
        checkpointer=checkpointer_manager.saver,
        vector_service=vector_service,
    )
    token_meter = TokenMeterCallbackHandler()
    lg_config = build_langgraph_config(
        thread_id=thread_id,
        user_id=current_user.id,
        feature="ingestion",
        extra_metadata={"doc_type": doc_type, "batch_id": str(batch.id)},
        extra_callbacks=[token_meter],
    )

    try:
        result = await graph.ainvoke(
            {
                "user_id": str(current_user.id),
                "account_id": str(account.id),
                "account_currency": account.currency,
                "document_id": str(document.id),
                "batch_id": str(batch.id),
                "filename": filename,
                "mime_type": mime_type,
                "doc_type": doc_type,
                "file_bytes_b64": base64.b64encode(raw_bytes).decode("ascii"),
                "categories": [
                    {"id": str(c.id), "name": c.name, "kind": c.kind} for c in categories
                ],
                "rules": [
                    {
                        "match_pattern": r.match_pattern,
                        "match_type": r.match_type,
                        "category_id": str(r.category_id),
                        "merchant_override": r.merchant_override,
                    }
                    for r in rules
                ],
                "existing_fingerprints": list(existing_fps),
            },
            config=lg_config,
        )
    except Exception as exc:
        batch.status = "failed"
        batch.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {exc}",
        ) from exc

    staged_rows = result.get("staged_rows", [])
    extracted_text = result.get("extracted_text", "")
    document.extracted_text = extracted_text

    # Index PDF/receipt text chunks into Upstash Vector for semantic RAG
    if doc_type in ("pdf_statement", "receipt") and extracted_text:
        await vector_service.upsert_document_chunks(
            user_id=current_user.id,
            document_id=document.id,
            chunks=_chunk_text(extracted_text),
            metadata={"filename": filename, "doc_type": doc_type, "account_id": str(account.id)},
        )

    staged_models: list[StagedTransaction] = []
    for row in staged_rows:
        raw_payload = dict(row.get("raw_payload") or {})
        raw_payload["__row_index"] = row["row_index"]
        staged_models.append(
            StagedTransaction(
                batch_id=batch.id,
                user_id=current_user.id,
                occurred_at=date.fromisoformat(row["occurred_at"]),
                amount=Decimal(row["amount"]),
                currency=row["currency"],
                direction=row["direction"],
                merchant_raw=row["merchant_raw"],
                merchant_clean=row["merchant_clean"],
                description=row.get("description"),
                suggested_category_id=(
                    UUID(row["suggested_category_id"])
                    if row.get("suggested_category_id")
                    else None
                ),
                confidence=Decimal(str(round(float(row.get("confidence", 0.5)), 3))),
                categorization_source=row.get("categorization_source", "heuristic"),
                fingerprint=row["fingerprint"],
                is_duplicate=bool(row.get("is_duplicate", False)),
                needs_review=bool(row.get("needs_review", True)),
                user_approved=bool(row.get("user_approved", True)),
                raw_payload=raw_payload,
            )
        )

    db.add_all(staged_models)
    batch.status = "needs_review"
    batch.total_rows = len(staged_models)
    batch.duplicate_rows = sum(1 for s in staged_models if s.is_duplicate)
    batch.needs_review_rows = sum(1 for s in staged_models if s.needs_review)
    batch.balance_reconciled = result.get("balance_reconciled")
    batch.reconciliation_note = result.get("reconciliation_note")

    await db.commit()

    if token_meter.total_tokens > 0:
        await record_ai_usage(
            db,
            user=current_user,
            feature="document_ingestion",
            prompt_tokens=token_meter.prompt_tokens,
            completion_tokens=token_meter.completion_tokens,
            total_tokens=token_meter.total_tokens,
            model_name=token_meter.model_name,
        )

    # Reload with relationships
    return await get_import_batch(batch.id, current_user=current_user, db=db)


@router.post("/{batch_id}/commit", response_model=ImportBatchDetailResponse)
async def commit_import_batch(
    batch_id: UUID,
    payload: ImportReviewCommitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> ImportBatchDetailResponse:
    """Resume the paused LangGraph HITL thread, commit approved transactions to Neon,
    and upsert confirmed merchant->category pairs into Upstash Vector."""
    batch = await db.scalar(
        select(ImportBatch)
        .options(selectinload(ImportBatch.document), selectinload(ImportBatch.staged_transactions))
        .where(ImportBatch.id == batch_id, ImportBatch.user_id == current_user.id)
    )
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found.")
    if batch.status == "committed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This import batch is already committed."
        )

    account = await db.get(Account, batch.account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target account missing.")

    staged_by_id = {s.id: s for s in batch.staged_transactions}
    graph_decisions: list[dict] = []

    for dec in payload.decisions:
        staged = staged_by_id.get(dec.staged_id)
        if staged is None:
            continue
        staged.user_approved = dec.user_approved
        if dec.merchant_clean is not None:
            staged.merchant_clean = dec.merchant_clean.strip()
        if dec.category_id is not None:
            staged.suggested_category_id = dec.category_id
        if dec.direction is not None:
            staged.direction = dec.direction
        if dec.amount is not None:
            staged.amount = dec.amount.quantize(Decimal("0.01"))
        if dec.occurred_at is not None:
            staged.occurred_at = dec.occurred_at
        if dec.description is not None:
            staged.description = dec.description

        row_index = int((staged.raw_payload or {}).get("__row_index", 0))
        graph_decisions.append(
            {
                "row_index": row_index,
                "user_approved": staged.user_approved,
                "merchant_clean": staged.merchant_clean,
                "category_id": str(staged.suggested_category_id)
                if staged.suggested_category_id
                else None,
                "direction": staged.direction,
                "amount": f"{staged.amount:.2f}",
                "occurred_at": staged.occurred_at.isoformat(),
                "description": staged.description,
            }
        )

    graph = build_ingestion_graph(
        checkpointer=checkpointer_manager.saver,
        vector_service=vector_service,
    )
    lg_config = build_langgraph_config(
        thread_id=batch.langgraph_thread_id,
        user_id=current_user.id,
        feature="ingestion_commit",
        extra_metadata={"batch_id": str(batch.id)},
    )

    # Resume the paused LangGraph thread; if checkpoint was cleared (e.g., MemorySaver restart),
    # fall back cleanly to the persisted staged_transactions in Neon.
    approved_rows: list[dict] = []
    learning_examples: list[dict[str, str]] = []

    state_snap = await graph.aget_state(lg_config)
    if state_snap and state_snap.next:
        final_state = await graph.ainvoke(
            Command(
                resume={
                    "decisions": graph_decisions,
                    "skip_duplicates": payload.skip_duplicates,
                    "learn_from_edits": payload.learn_from_edits,
                }
            ),
            config=lg_config,
        )
        approved_rows = final_state.get("approved_rows", [])
        learning_examples = final_state.get("learning_examples", [])
    else:
        categories = {
            c.id: c.name
            for c in (
                await db.scalars(select(Category).where(Category.user_id == current_user.id))
            ).all()
        }
        for s in batch.staged_transactions:
            if payload.skip_duplicates and s.is_duplicate and not s.user_approved:
                continue
            if not s.user_approved:
                continue
            approved_rows.append(
                {
                    "occurred_at": s.occurred_at.isoformat(),
                    "amount": f"{s.amount:.2f}",
                    "currency": s.currency,
                    "direction": s.direction,
                    "merchant_raw": s.merchant_raw,
                    "merchant_clean": s.merchant_clean,
                    "description": s.description,
                    "suggested_category_id": str(s.suggested_category_id)
                    if s.suggested_category_id
                    else None,
                    "confidence": float(s.confidence),
                }
            )
            if payload.learn_from_edits and s.suggested_category_id:
                learning_examples.append(
                    {
                        "merchant_raw": s.merchant_raw,
                        "merchant_clean": s.merchant_clean,
                        "category_id": str(s.suggested_category_id),
                        "category_name": categories.get(s.suggested_category_id, ""),
                    }
                )

    # Persist approved transactions to Neon ledger
    created_count = 0
    for row in approved_rows:
        occ = date.fromisoformat(row["occurred_at"])
        amt = Decimal(str(row["amount"])).quantize(Decimal("0.01"))
        direction = row["direction"]
        fp = compute_transaction_fingerprint(
            account_id=account.id,
            occurred_at=occ,
            amount=amt,
            direction=direction,
            merchant_raw=row["merchant_raw"],
        )
        tx = Transaction(
            user_id=current_user.id,
            account_id=account.id,
            category_id=(
                UUID(row["suggested_category_id"]) if row.get("suggested_category_id") else None
            ),
            amount=amt,
            currency=row.get("currency", account.currency),
            base_amount=amt,
            fx_rate=Decimal("1.000000"),
            direction=direction,
            occurred_at=occ,
            merchant_raw=row["merchant_raw"],
            merchant_clean=row["merchant_clean"],
            description=row.get("description"),
            tags=["imported"],
            fingerprint=fp,
            source_document_id=batch.document_id,
            ai_confidence=Decimal(str(round(float(row.get("confidence", 0.9)), 3))),
        )
        db.add(tx)
        created_count += 1

    await db.flush()
    await recalculate_account_balance(db, account)

    batch.status = "committed"
    batch.committed_rows = created_count
    await db.commit()

    # Upsert confirmed merchant -> category pairs into Upstash Vector for self-learning
    seen_merchants: set[str] = set()
    for ex in learning_examples:
        key = ex["merchant_raw"].lower().strip()
        if key and key not in seen_merchants:
            seen_merchants.add(key)
            await vector_service.upsert_merchant_memory(
                user_id=current_user.id,
                merchant_raw=ex["merchant_raw"],
                merchant_clean=ex["merchant_clean"],
                category_id=ex["category_id"],
                category_name=ex["category_name"],
            )

    return await get_import_batch(batch.id, current_user=current_user, db=db)
