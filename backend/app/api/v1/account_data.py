import csv
import io
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_vector_dep
from app.core.database import get_db
from app.core.security import verify_password
from app.models.advisor import ChatThread
from app.models.audit import AuditLog
from app.models.finance import Account, CategorizationRule, Category, Transaction
from app.models.planning import Budget, FinancialGoal, NetWorthSnapshot, RecurringItem
from app.models.user import User
from app.services.vector_service import VectorMemoryBackend

router = APIRouter(prefix="/data", tags=["Data Export, Privacy & Audit Logs"])


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    details: dict[str, Any]
    created_at: datetime


class DeleteAccountRequest(BaseModel):
    password: str
    confirm_phrase: str


async def record_audit(
    db: AsyncSession,
    *,
    user_id: UUID,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    ip_address: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            details=details or {},
        )
    )
    await db.commit()


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    rows = (
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == current_user.id)
            .order_by(AuditLog.created_at.desc())
            .limit(50)
        )
    ).all()
    return [AuditLogResponse.model_validate(r) for r in rows]


@router.get("/export/csv")
async def export_transactions_csv(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    accounts = {
        a.id: a.name
        for a in (await db.scalars(select(Account).where(Account.user_id == current_user.id))).all()
    }
    categories = {
        c.id: c.name
        for c in (await db.scalars(select(Category).where(Category.user_id == current_user.id))).all()
    }
    txs = (
        await db.scalars(
            select(Transaction)
            .where(Transaction.user_id == current_user.id)
            .order_by(Transaction.occurred_at.desc(), Transaction.created_at.desc())
        )
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Date",
            "Account",
            "Merchant",
            "Raw Merchant",
            "Category",
            "Direction",
            "Amount",
            "Currency",
            "Base Amount",
            "Is Transfer",
            "Description",
            "Notes",
        ]
    )
    for tx in txs:
        writer.writerow(
            [
                tx.occurred_at.isoformat(),
                accounts.get(tx.account_id, ""),
                tx.merchant_clean,
                tx.merchant_raw,
                categories.get(tx.category_id, "Uncategorized") if tx.category_id else "Uncategorized",
                tx.direction,
                f"{tx.amount:.2f}",
                tx.currency,
                f"{tx.base_amount:.2f}",
                "true" if tx.is_transfer else "false",
                tx.description or "",
                tx.notes or "",
            ]
        )

    await record_audit(
        db,
        user_id=current_user.id,
        action="data.export_csv",
        resource_type="transactions",
        ip_address=request.client.host if request.client else None,
        details={"row_count": len(txs)},
    )

    filename = f"financinio_transactions_{date.today().isoformat()}.csv"
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/json")
async def export_full_json_backup(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    accounts = (await db.scalars(select(Account).where(Account.user_id == current_user.id))).all()
    categories = (await db.scalars(select(Category).where(Category.user_id == current_user.id))).all()
    rules = (
        await db.scalars(
            select(CategorizationRule).where(CategorizationRule.user_id == current_user.id)
        )
    ).all()
    txs = (
        await db.scalars(
            select(Transaction)
            .where(Transaction.user_id == current_user.id)
            .order_by(Transaction.occurred_at.desc())
        )
    ).all()
    budgets = (await db.scalars(select(Budget).where(Budget.user_id == current_user.id))).all()
    recurring = (
        await db.scalars(select(RecurringItem).where(RecurringItem.user_id == current_user.id))
    ).all()
    snapshots = (
        await db.scalars(
            select(NetWorthSnapshot).where(NetWorthSnapshot.user_id == current_user.id)
        )
    ).all()
    goals = (
        await db.scalars(select(FinancialGoal).where(FinancialGoal.user_id == current_user.id))
    ).all()
    threads = (
        await db.scalars(select(ChatThread).where(ChatThread.user_id == current_user.id))
    ).all()

    await record_audit(
        db,
        user_id=current_user.id,
        action="data.export_json",
        resource_type="workspace",
        ip_address=request.client.host if request.client else None,
        details={"transactions": len(txs), "accounts": len(accounts)},
    )

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "version": "1.0",
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "full_name": current_user.full_name,
            "base_currency": current_user.base_currency,
            "fiscal_start_day": current_user.fiscal_start_day,
        },
        "accounts": [
            {
                "id": str(a.id),
                "name": a.name,
                "type": a.type,
                "currency": a.currency,
                "initial_balance": f"{a.initial_balance:.2f}",
                "current_balance": f"{a.current_balance:.2f}",
                "institution": a.institution,
            }
            for a in accounts
        ],
        "categories": [
            {"id": str(c.id), "name": c.name, "kind": c.kind, "color": c.color} for c in categories
        ],
        "rules": [
            {
                "id": str(r.id),
                "match_pattern": r.match_pattern,
                "match_type": r.match_type,
                "category_id": str(r.category_id),
                "merchant_override": r.merchant_override,
            }
            for r in rules
        ],
        "transactions": [
            {
                "id": str(t.id),
                "account_id": str(t.account_id),
                "category_id": str(t.category_id) if t.category_id else None,
                "occurred_at": t.occurred_at.isoformat(),
                "direction": t.direction,
                "amount": f"{t.amount:.2f}",
                "currency": t.currency,
                "merchant_clean": t.merchant_clean,
                "merchant_raw": t.merchant_raw,
                "is_transfer": t.is_transfer,
                "notes": t.notes,
            }
            for t in txs
        ],
        "budgets": [
            {
                "id": str(b.id),
                "category_id": str(b.category_id),
                "amount": f"{b.amount:.2f}",
                "period": b.period,
                "rollover": b.rollover,
            }
            for b in budgets
        ],
        "recurring_items": [
            {
                "id": str(r.id),
                "merchant_name": r.merchant_name,
                "amount": f"{r.amount:.2f}",
                "cadence": r.cadence,
                "next_due_date": r.next_due_date.isoformat(),
            }
            for r in recurring
        ],
        "net_worth_snapshots": [
            {
                "snapshot_date": s.snapshot_date.isoformat(),
                "total_assets": f"{s.total_assets:.2f}",
                "total_liabilities": f"{s.total_liabilities:.2f}",
                "net_worth": f"{s.net_worth:.2f}",
            }
            for s in snapshots
        ],
        "financial_goals": [
            {
                "id": str(g.id),
                "name": g.name,
                "goal_type": g.goal_type,
                "target_amount": f"{g.target_amount:.2f}",
                "current_amount": f"{g.current_amount:.2f}",
                "monthly_contribution": f"{g.monthly_contribution:.2f}",
            }
            for g in goals
        ],
        "chat_thread_count": len(threads),
    }


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_account(
    payload: DeleteAccountRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> None:
    if payload.confirm_phrase.strip().upper() != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Confirmation phrase must be exactly "DELETE MY ACCOUNT".',
        )
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )

    uid = current_user.id
    await vector_service.purge_user_namespaces(uid)
    await db.delete(current_user)
    await db.commit()
    response.delete_cookie("financinio_refresh_token", path="/")
