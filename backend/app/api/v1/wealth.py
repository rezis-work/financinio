from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.planning import FinancialGoal
from app.models.user import User
from app.schemas.planning import (
    DebtPayoffComparisonResponse,
    DebtPayoffRequest,
    GoalContributeRequest,
    GoalCreate,
    GoalResponse,
    GoalUpdate,
    NetWorthOverviewResponse,
    NetWorthSnapshotResponse,
    WhatIfRequest,
    WhatIfResponse,
)
from app.services.planning_service import (
    capture_net_worth_snapshot,
    enrich_goal,
    get_net_worth_overview,
    simulate_debt_payoff,
    simulate_what_if,
)

router = APIRouter(prefix="/wealth", tags=["Wealth, Goals & Simulators"])


# --- Net Worth ---


@router.get("/net-worth", response_model=NetWorthOverviewResponse)
async def net_worth_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NetWorthOverviewResponse:
    return await get_net_worth_overview(db, current_user)


@router.post(
    "/net-worth/snapshot",
    response_model=NetWorthSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_net_worth_snapshot(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NetWorthSnapshotResponse:
    return await capture_net_worth_snapshot(db, current_user)


# --- Financial Goals ---


@router.get("/goals", response_model=list[GoalResponse])
async def list_goals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GoalResponse]:
    goals = (
        await db.scalars(
            select(FinancialGoal)
            .where(FinancialGoal.user_id == current_user.id)
            .order_by(FinancialGoal.is_completed.asc(), FinancialGoal.created_at.desc())
        )
    ).all()
    return [enrich_goal(g) for g in goals]


@router.post("/goals", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    goal = FinancialGoal(
        user_id=current_user.id,
        linked_account_id=payload.linked_account_id,
        name=payload.name.strip(),
        goal_type=payload.goal_type,
        target_amount=payload.target_amount,
        current_amount=payload.current_amount,
        monthly_contribution=payload.monthly_contribution,
        target_date=payload.target_date,
        color=payload.color,
        is_completed=payload.current_amount >= payload.target_amount,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return enrich_goal(goal)


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: UUID,
    payload: GoalUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    goal = await db.scalar(
        select(FinancialGoal).where(
            FinancialGoal.id == goal_id, FinancialGoal.user_id == current_user.id
        )
    )
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")

    if payload.name is not None:
        goal.name = payload.name.strip()
    if payload.goal_type is not None:
        goal.goal_type = payload.goal_type
    if payload.target_amount is not None:
        goal.target_amount = payload.target_amount
    if payload.current_amount is not None:
        goal.current_amount = payload.current_amount
    if payload.monthly_contribution is not None:
        goal.monthly_contribution = payload.monthly_contribution
    if payload.target_date is not None:
        goal.target_date = payload.target_date
    if payload.linked_account_id is not None:
        goal.linked_account_id = payload.linked_account_id
    if payload.color is not None:
        goal.color = payload.color
    if payload.is_completed is not None:
        goal.is_completed = payload.is_completed
    elif goal.current_amount >= goal.target_amount:
        goal.is_completed = True

    await db.commit()
    await db.refresh(goal)
    return enrich_goal(goal)


@router.post("/goals/{goal_id}/contribute", response_model=GoalResponse)
async def contribute_to_goal(
    goal_id: UUID,
    payload: GoalContributeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    goal = await db.scalar(
        select(FinancialGoal).where(
            FinancialGoal.id == goal_id, FinancialGoal.user_id == current_user.id
        )
    )
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")

    goal.current_amount += payload.amount
    if goal.current_amount >= goal.target_amount:
        goal.is_completed = True
    await db.commit()
    await db.refresh(goal)
    return enrich_goal(goal)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    goal = await db.scalar(
        select(FinancialGoal).where(
            FinancialGoal.id == goal_id, FinancialGoal.user_id == current_user.id
        )
    )
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
    await db.delete(goal)
    await db.commit()


# --- Simulators ---


@router.post("/simulate/debt-payoff", response_model=DebtPayoffComparisonResponse)
async def run_debt_payoff_simulation(
    payload: DebtPayoffRequest,
    current_user: User = Depends(get_current_user),
) -> DebtPayoffComparisonResponse:
    return simulate_debt_payoff(payload)


@router.post("/simulate/what-if", response_model=WhatIfResponse)
async def run_what_if_simulation(
    payload: WhatIfRequest,
    current_user: User = Depends(get_current_user),
) -> WhatIfResponse:
    return simulate_what_if(payload)
