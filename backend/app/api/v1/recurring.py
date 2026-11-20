from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.planning import RecurringItem
from app.models.user import User
from app.schemas.planning import (
    DetectRecurringResponse,
    RecurringCreate,
    RecurringItemResponse,
    RecurringOverviewResponse,
    RecurringUpdate,
)
from app.services.planning_service import (
    _recurring_to_response,
    detect_recurring_from_ledger,
    get_recurring_overview,
)

router = APIRouter(prefix="/recurring", tags=["Recurring & Subscriptions"])


@router.get("", response_model=RecurringOverviewResponse)
async def list_recurring(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecurringOverviewResponse:
    return await get_recurring_overview(db, current_user)


@router.post("/detect", response_model=DetectRecurringResponse)
async def detect_recurring(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DetectRecurringResponse:
    return await detect_recurring_from_ledger(db, current_user)


@router.post("", response_model=RecurringItemResponse, status_code=status.HTTP_201_CREATED)
async def create_recurring(
    payload: RecurringCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecurringItemResponse:
    item = RecurringItem(
        user_id=current_user.id,
        account_id=payload.account_id,
        category_id=payload.category_id,
        merchant_name=payload.merchant_name.strip(),
        amount=payload.amount,
        currency=payload.currency.upper(),
        direction=payload.direction,
        cadence=payload.cadence,
        next_due_date=payload.next_due_date,
        is_subscription=payload.is_subscription,
        auto_detected=False,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _recurring_to_response(item)


@router.patch("/{item_id}", response_model=RecurringItemResponse)
async def update_recurring(
    item_id: UUID,
    payload: RecurringUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecurringItemResponse:
    item = await db.scalar(
        select(RecurringItem).where(
            RecurringItem.id == item_id, RecurringItem.user_id == current_user.id
        )
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recurring item not found."
        )

    if payload.merchant_name is not None:
        item.merchant_name = payload.merchant_name.strip()
    if payload.amount is not None:
        item.amount = payload.amount
    if payload.cadence is not None:
        item.cadence = payload.cadence
    if payload.next_due_date is not None:
        item.next_due_date = payload.next_due_date
    if payload.category_id is not None:
        item.category_id = payload.category_id
    if payload.is_subscription is not None:
        item.is_subscription = payload.is_subscription
    if payload.is_active is not None:
        item.is_active = payload.is_active

    await db.commit()
    await db.refresh(item)
    return _recurring_to_response(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring(
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    item = await db.scalar(
        select(RecurringItem).where(
            RecurringItem.id == item_id, RecurringItem.user_id == current_user.id
        )
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recurring item not found."
        )
    await db.delete(item)
    await db.commit()
