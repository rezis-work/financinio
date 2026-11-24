import hashlib
import re
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Account, Transaction


def normalize_merchant_name(raw: str) -> str:
    """Basic deterministic merchant cleanup before LLM/memory enrichment."""
    text = raw.strip()
    text = re.sub(r"\s+", " ", text)
    # Strip trailing store/reference codes like *1A2B3C or #4491
    cleaned = re.sub(r"(\*[A-Z0-9]{4,}|#\d{3,})$", "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^(POS|ACH|DEBIT|CREDIT|CARD PURCHASE|SQ \*|TST\*)\s*", "", cleaned, flags=re.IGNORECASE).strip()
    if cleaned.isupper() and len(cleaned) > 3:
        cleaned = cleaned.title()
    return cleaned or text or "Unknown Merchant"


def compute_transaction_fingerprint(
    account_id: UUID,
    occurred_at: date,
    amount: Decimal,
    direction: str,
    merchant_raw: str,
) -> str:
    # Keep Unicode letters/digits (e.g., Georgian Mkhedruli) so non-Latin merchants never collide
    normalized = re.sub(r"[\W_]+", "", merchant_raw.lower())[:64]
    canonical = f"{account_id}|{occurred_at.isoformat()}|{amount:.2f}|{direction}|{normalized}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def recalculate_account_balance(db: AsyncSession, account: Account) -> Decimal:
    """Recompute account current_balance from initial_balance + ledger delta."""
    signed_sum_expr = func.coalesce(
        func.sum(
            case(
                (Transaction.direction == "inflow", Transaction.amount),
                else_=-Transaction.amount,
            )
        ),
        Decimal("0.00"),
    )
    delta = await db.scalar(
        select(signed_sum_expr).where(
            Transaction.account_id == account.id,
            Transaction.parent_transaction_id.is_(None),
        )
    )
    new_balance = (account.initial_balance + (delta or Decimal("0.00"))).quantize(Decimal("0.01"))
    account.current_balance = new_balance
    return new_balance
