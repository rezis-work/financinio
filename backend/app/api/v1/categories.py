from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.finance import CategorizationRule, Category
from app.models.user import User
from app.schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    RuleCreate,
    RuleResponse,
)

router = APIRouter(prefix="/categories", tags=["Categories & Rules"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryResponse]:
    rows = (
        await db.scalars(
            select(Category)
            .where(Category.user_id == current_user.id)
            .order_by(Category.kind.asc(), Category.name.asc())
        )
    ).all()
    return [CategoryResponse.model_validate(c) for c in rows]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    cat = Category(
        user_id=current_user.id,
        name=payload.name.strip(),
        kind=payload.kind,
        icon=payload.icon,
        color=payload.color,
        parent_id=payload.parent_id,
        is_system=False,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return CategoryResponse.model_validate(cat)


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    cat = await db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == current_user.id)
    )
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    if payload.name is not None:
        cat.name = payload.name.strip()
    if payload.kind is not None:
        cat.kind = payload.kind
    if payload.icon is not None:
        cat.icon = payload.icon
    if payload.color is not None:
        cat.color = payload.color
    if payload.parent_id is not None:
        cat.parent_id = payload.parent_id

    await db.commit()
    await db.refresh(cat)
    return CategoryResponse.model_validate(cat)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    cat = await db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == current_user.id)
    )
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    await db.delete(cat)
    await db.commit()


# --- Tier 1 Deterministic Categorization Rules ---


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RuleResponse]:
    rows = (
        await db.scalars(
            select(CategorizationRule)
            .where(CategorizationRule.user_id == current_user.id)
            .order_by(CategorizationRule.priority.asc(), CategorizationRule.created_at.desc())
        )
    ).all()
    return [RuleResponse.model_validate(r) for r in rows]


@router.post("/rules", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    cat = await db.scalar(
        select(Category).where(
            Category.id == payload.category_id, Category.user_id == current_user.id
        )
    )
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    rule = CategorizationRule(
        user_id=current_user.id,
        match_pattern=payload.match_pattern.strip(),
        match_type=payload.match_type,
        category_id=cat.id,
        merchant_override=payload.merchant_override.strip() if payload.merchant_override else None,
        priority=payload.priority,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return RuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    rule = await db.scalar(
        select(CategorizationRule).where(
            CategorizationRule.id == rule_id, CategorizationRule.user_id == current_user.id
        )
    )
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    await db.delete(rule)
    await db.commit()
