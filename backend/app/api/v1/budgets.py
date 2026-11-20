from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.finance import Category
from app.models.planning import Budget
from app.models.user import User
from app.schemas.planning import (
    ApplyBudgetTemplateRequest,
    BudgetCreate,
    BudgetOverviewResponse,
    BudgetUpdate,
)
from app.services.planning_service import apply_50_30_20_template, get_budget_overview

router = APIRouter(prefix="/budgets", tags=["Budgets"])


@router.get("", response_model=BudgetOverviewResponse)
async def list_budgets(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetOverviewResponse:
    return await get_budget_overview(db, current_user, target_month=month)


@router.post("", response_model=BudgetOverviewResponse, status_code=status.HTTP_201_CREATED)
async def create_or_upsert_budget(
    payload: BudgetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetOverviewResponse:
    cat = await db.scalar(
        select(Category).where(
            Category.id == payload.category_id, Category.user_id == current_user.id
        )
    )
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    existing = await db.scalar(
        select(Budget).where(
            Budget.user_id == current_user.id,
            Budget.category_id == payload.category_id,
            Budget.period == payload.period,
        )
    )
    if existing is not None:
        existing.amount = payload.amount
        existing.rollover = payload.rollover
        existing.alert_threshold_pct = payload.alert_threshold_pct
        existing.is_active = True
    else:
        db.add(
            Budget(
                user_id=current_user.id,
                category_id=payload.category_id,
                amount=payload.amount,
                period=payload.period,
                rollover=payload.rollover,
                alert_threshold_pct=payload.alert_threshold_pct,
            )
        )
    await db.commit()
    return await get_budget_overview(db, current_user)


@router.post("/apply-50-30-20", response_model=BudgetOverviewResponse)
async def apply_template(
    payload: ApplyBudgetTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetOverviewResponse:
    return await apply_50_30_20_template(db, current_user, payload.monthly_income)


@router.patch("/{budget_id}", response_model=BudgetOverviewResponse)
async def update_budget(
    budget_id: UUID,
    payload: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetOverviewResponse:
    budget = await db.scalar(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == current_user.id)
    )
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found.")

    if payload.amount is not None:
        budget.amount = payload.amount
    if payload.rollover is not None:
        budget.rollover = payload.rollover
    if payload.alert_threshold_pct is not None:
        budget.alert_threshold_pct = payload.alert_threshold_pct
    if payload.is_active is not None:
        budget.is_active = payload.is_active

    await db.commit()
    return await get_budget_overview(db, current_user)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    budget = await db.scalar(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == current_user.id)
    )
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found.")
    await db.delete(budget)
    await db.commit()
