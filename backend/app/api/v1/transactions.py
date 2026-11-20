from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_vector_dep
from app.core.database import get_db
from app.models.finance import Account, Category, Transaction
from app.models.user import User
from app.schemas.transaction import (
    BulkCategorizeRequest,
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
)
from app.services.ledger_service import (
    compute_transaction_fingerprint,
    normalize_merchant_name,
    recalculate_account_balance,
)
from app.services.vector_service import VectorMemoryBackend

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    search: str | None = Query(default=None),
    account_id: UUID | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    direction: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionListResponse:
    filters = [
        Transaction.user_id == current_user.id,
        Transaction.parent_transaction_id.is_(None),
    ]
    if account_id is not None:
        filters.append(Transaction.account_id == account_id)
    if category_id is not None:
        filters.append(Transaction.category_id == category_id)
    if direction in ("inflow", "outflow"):
        filters.append(Transaction.direction == direction)
    if date_from is not None:
        filters.append(Transaction.occurred_at >= date_from)
    if date_to is not None:
        filters.append(Transaction.occurred_at <= date_to)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Transaction.merchant_clean.ilike(pattern),
                Transaction.merchant_raw.ilike(pattern),
                Transaction.description.ilike(pattern),
                Transaction.notes.ilike(pattern),
            )
        )

    total = await db.scalar(select(func.count(Transaction.id)).where(*filters)) or 0
    rows = (
        await db.scalars(
            select(Transaction)
            .where(*filters)
            .order_by(Transaction.occurred_at.desc(), Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    account = await db.scalar(
        select(Account).where(Account.id == payload.account_id, Account.user_id == current_user.id)
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    if payload.category_id is not None:
        cat = await db.scalar(
            select(Category).where(
                Category.id == payload.category_id, Category.user_id == current_user.id
            )
        )
        if cat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    currency = (payload.currency or account.currency).upper()
    amount = payload.amount.quantize(Decimal("0.01"))
    base_amount = (amount * payload.fx_rate).quantize(Decimal("0.01"))
    merchant_raw = payload.merchant.strip()
    merchant_clean = normalize_merchant_name(merchant_raw)
    fp = compute_transaction_fingerprint(
        account_id=account.id,
        occurred_at=payload.occurred_at,
        amount=amount,
        direction=payload.direction,
        merchant_raw=merchant_raw,
    )

    tx = Transaction(
        user_id=current_user.id,
        account_id=account.id,
        category_id=payload.category_id,
        amount=amount,
        currency=currency,
        base_amount=base_amount,
        fx_rate=payload.fx_rate,
        direction=payload.direction,
        occurred_at=payload.occurred_at,
        merchant_raw=merchant_raw,
        merchant_clean=merchant_clean,
        description=payload.description,
        notes=payload.notes,
        tags=payload.tags,
        fingerprint=fp,
        is_transfer=payload.is_transfer or payload.transfer_account_id is not None,
    )
    db.add(tx)
    await db.flush()

    # Optional linked internal transfer peer leg
    if payload.transfer_account_id is not None and payload.transfer_account_id != account.id:
        peer_acc = await db.scalar(
            select(Account).where(
                Account.id == payload.transfer_account_id, Account.user_id == current_user.id
            )
        )
        if peer_acc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Transfer target account not found."
            )
        peer_dir = "inflow" if payload.direction == "outflow" else "outflow"
        peer_fp = compute_transaction_fingerprint(
            account_id=peer_acc.id,
            occurred_at=payload.occurred_at,
            amount=amount,
            direction=peer_dir,
            merchant_raw=f"Transfer: {account.name}",
        )
        peer_tx = Transaction(
            user_id=current_user.id,
            account_id=peer_acc.id,
            category_id=payload.category_id,
            amount=amount,
            currency=peer_acc.currency,
            base_amount=base_amount,
            fx_rate=payload.fx_rate,
            direction=peer_dir,
            occurred_at=payload.occurred_at,
            merchant_raw=f"Transfer: {account.name}",
            merchant_clean=f"Transfer: {account.name}",
            description=payload.description,
            notes=payload.notes,
            tags=payload.tags,
            fingerprint=peer_fp,
            is_transfer=True,
            transfer_peer_id=tx.id,
        )
        db.add(peer_tx)
        await db.flush()
        tx.transfer_peer_id = peer_tx.id
        await recalculate_account_balance(db, peer_acc)

    await recalculate_account_balance(db, account)
    await db.commit()
    await db.refresh(tx)
    return TransactionResponse.model_validate(tx)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: UUID,
    payload: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> TransactionResponse:
    tx = await db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.user_id == current_user.id
        )
    )
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")

    old_account_id = tx.account_id
    category_changed_to: Category | None = None

    if payload.account_id is not None and payload.account_id != tx.account_id:
        new_acc = await db.scalar(
            select(Account).where(
                Account.id == payload.account_id, Account.user_id == current_user.id
            )
        )
        if new_acc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
        tx.account_id = new_acc.id

    if payload.category_id is not None:
        cat = await db.scalar(
            select(Category).where(
                Category.id == payload.category_id, Category.user_id == current_user.id
            )
        )
        if cat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
        tx.category_id = cat.id
        category_changed_to = cat

    if payload.amount is not None:
        tx.amount = payload.amount.quantize(Decimal("0.01"))
        tx.base_amount = (tx.amount * tx.fx_rate).quantize(Decimal("0.01"))
    if payload.direction is not None:
        tx.direction = payload.direction
    if payload.occurred_at is not None:
        tx.occurred_at = payload.occurred_at
    if payload.merchant_clean is not None:
        tx.merchant_clean = payload.merchant_clean.strip()
    if payload.description is not None:
        tx.description = payload.description
    if payload.notes is not None:
        tx.notes = payload.notes
    if payload.tags is not None:
        tx.tags = payload.tags
    if payload.is_transfer is not None:
        tx.is_transfer = payload.is_transfer

    await db.flush()
    for acc_id in {old_account_id, tx.account_id}:
        acc = await db.get(Account, acc_id)
        if acc is not None:
            await recalculate_account_balance(db, acc)

    await db.commit()
    await db.refresh(tx)

    # Self-learning feedback into Upstash Vector whenever user corrects category
    if category_changed_to is not None:
        await vector_service.upsert_merchant_memory(
            user_id=current_user.id,
            merchant_raw=tx.merchant_raw,
            merchant_clean=tx.merchant_clean,
            category_id=str(category_changed_to.id),
            category_name=category_changed_to.name,
        )

    return TransactionResponse.model_validate(tx)


@router.post("/bulk-categorize")
async def bulk_categorize(
    payload: BulkCategorizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> dict[str, int]:
    cat: Category | None = None
    if payload.category_id is not None:
        cat = await db.scalar(
            select(Category).where(
                Category.id == payload.category_id, Category.user_id == current_user.id
            )
        )
        if cat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    txs = (
        await db.scalars(
            select(Transaction).where(
                Transaction.user_id == current_user.id,
                Transaction.id.in_(payload.transaction_ids),
            )
        )
    ).all()

    for tx in txs:
        tx.category_id = cat.id if cat else None
    await db.commit()

    if payload.learn_memory and cat is not None:
        seen_merchants: set[str] = set()
        for tx in txs:
            key = tx.merchant_raw.lower()
            if key not in seen_merchants:
                seen_merchants.add(key)
                await vector_service.upsert_merchant_memory(
                    user_id=current_user.id,
                    merchant_raw=tx.merchant_raw,
                    merchant_clean=tx.merchant_clean,
                    category_id=str(cat.id),
                    category_name=cat.name,
                )

    return {"updated": len(txs)}


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    tx = await db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.user_id == current_user.id
        )
    )
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    account = await db.get(Account, tx.account_id)
    await db.delete(tx)
    await db.flush()
    if account is not None:
        await recalculate_account_balance(db, account)
    await db.commit()
