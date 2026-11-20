from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.finance import Account
from app.models.user import User
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AccountResponse]:
    stmt = select(Account).where(Account.user_id == current_user.id)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    stmt = stmt.order_by(Account.created_at.asc())
    rows = (await db.scalars(stmt)).all()
    return [AccountResponse.model_validate(a) for a in rows]


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    account = Account(
        user_id=current_user.id,
        name=payload.name.strip(),
        type=payload.type,
        currency=payload.currency.upper(),
        initial_balance=payload.initial_balance,
        current_balance=payload.initial_balance,
        institution=payload.institution.strip() if payload.institution else None,
        color=payload.color,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return AccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: UUID,
    payload: AccountUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    account = await db.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    if payload.name is not None:
        account.name = payload.name.strip()
    if payload.type is not None:
        account.type = payload.type
    if payload.institution is not None:
        account.institution = payload.institution.strip() or None
    if payload.color is not None:
        account.color = payload.color
    if payload.is_archived is not None:
        account.is_archived = payload.is_archived

    await db.commit()
    await db.refresh(account)
    return AccountResponse.model_validate(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    account = await db.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    await db.delete(account)
    await db.commit()
