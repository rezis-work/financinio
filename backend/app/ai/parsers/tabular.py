import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field

from app.services.ledger_service import normalize_merchant_name


@dataclass
class ParsedTransactionRow:
    occurred_at: date
    amount: Decimal
    currency: str
    direction: Literal["inflow", "outflow"]
    merchant_raw: str
    merchant_clean: str
    description: str | None
    raw_payload: dict


class ColumnMappingSchema(BaseModel):
    date_column: str = Field(description="Header name for the transaction date")
    description_column: str = Field(description="Header name for merchant/description")
    amount_column: str | None = Field(
        default=None, description="Single signed amount column, if present"
    )
    debit_column: str | None = Field(
        default=None, description="Outflow/debit column, if split debit/credit"
    )
    credit_column: str | None = Field(
        default=None, description="Inflow/credit column, if split debit/credit"
    )
    currency_column: str | None = Field(default=None, description="Optional currency code column")


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%b %d, %Y",
    "%d %b %Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def parse_flexible_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    # Strip trailing timezone like Z or +00:00
    cleaned = re.sub(r"(Z|[+-]\d{2}:?\d{2})$", "", raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError:
        return None


def parse_flexible_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    raw = str(value).strip()
    if not raw or raw in {"-", "--", "N/A", "null", "None"}:
        return None
    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1].strip()
    # Remove currency symbols and spaces
    raw = re.sub(r"[$€£¥GEL\s]", "", raw, flags=re.IGNORECASE)
    # Handle European decimal comma (e.g. 1.234,56) vs US (1,234.56)
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw and raw.count(",") == 1 and len(raw.split(",")[1]) == 2:
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        dec = Decimal(raw)
        return -abs(dec) if negative else dec
    except InvalidOperation:
        return None


def _heuristic_map_columns(headers: list[str]) -> ColumnMappingSchema | None:
    lower_map = {h.lower().strip(): h for h in headers if h}

    def find_first(candidates: tuple[str, ...]) -> str | None:
        for cand in candidates:
            for low, orig in lower_map.items():
                if low == cand or cand in low:
                    return orig
        return None

    date_col = find_first(("date", "posted", "booking", "time", "occurred"))
    desc_col = find_first(("description", "merchant", "payee", "name", "memo", "details", "narrative"))
    amount_col = find_first(("amount", "value", "total", "sum"))
    debit_col = find_first(("debit", "withdrawal", "outflow", "expense", "charge", "paid out"))
    credit_col = find_first(("credit", "deposit", "inflow", "income", "paid in"))
    curr_col = find_first(("currency", "ccy"))

    if date_col and desc_col and (amount_col or debit_col or credit_col):
        return ColumnMappingSchema(
            date_column=date_col,
            description_column=desc_col,
            amount_column=amount_col,
            debit_column=debit_col,
            credit_column=credit_col,
            currency_column=curr_col,
        )
    return None


async def _llm_map_columns(
    headers: list[str],
    sample_rows: list[dict],
    llm: BaseChatModel,
) -> ColumnMappingSchema:
    structured = llm.with_structured_output(ColumnMappingSchema)
    prompt = (
        "Map the CSV/Excel bank statement columns to standard fields.\n"
        f"Headers: {headers}\n"
        f"Sample rows: {sample_rows[:3]}\n"
        "Return exact header names from the Headers list."
    )
    return await structured.ainvoke(prompt)  # type: ignore[return-value]


def _read_csv_rows(data: bytes) -> tuple[list[str], list[dict]]:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [h.strip() for h in (reader.fieldnames or []) if h]
    rows: list[dict] = []
    for row in reader:
        cleaned = {(k.strip() if k else ""): v for k, v in row.items()}
        if any(str(v or "").strip() for v in cleaned.values()):
            rows.append(cleaned)
    return headers, rows


def _read_xlsx_rows(data: bytes) -> tuple[list[str], list[dict]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    raw_rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not raw_rows:
        return [], []
    # Find first non-empty header row
    header_idx = 0
    for idx, row in enumerate(raw_rows[:10]):
        non_empty = [c for c in row if c is not None and str(c).strip()]
        if len(non_empty) >= 2:
            header_idx = idx
            break
    headers = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(raw_rows[header_idx])]
    rows: list[dict] = []
    for raw_row in raw_rows[header_idx + 1 :]:
        row_dict = {headers[i]: raw_row[i] for i in range(min(len(headers), len(raw_row)))}
        if any(v is not None and str(v).strip() for v in row_dict.values()):
            rows.append(row_dict)
    return headers, rows


async def parse_tabular_statement(
    *,
    data: bytes,
    doc_type: Literal["csv", "xlsx"],
    default_currency: str,
    llm: BaseChatModel | None = None,
) -> tuple[list[ParsedTransactionRow], str]:
    headers, rows = _read_csv_rows(data) if doc_type == "csv" else _read_xlsx_rows(data)
    if not headers or not rows:
        return [], ""

    mapping = _heuristic_map_columns(headers)
    if mapping is None and llm is not None:
        mapping = await _llm_map_columns(headers, rows, llm)
    if mapping is None:
        raise ValueError(
            f"Could not map statement columns automatically. Detected headers: {headers}"
        )

    parsed: list[ParsedTransactionRow] = []
    for row in rows:
        tx_date = parse_flexible_date(row.get(mapping.date_column))
        if tx_date is None:
            continue

        raw_desc = str(row.get(mapping.description_column) or "").strip()
        if not raw_desc:
            raw_desc = "Bank Transaction"

        direction: Literal["inflow", "outflow"] = "outflow"
        amount: Decimal | None = None

        if mapping.debit_column or mapping.credit_column:
            debit = parse_flexible_decimal(row.get(mapping.debit_column)) if mapping.debit_column else None
            credit = parse_flexible_decimal(row.get(mapping.credit_column)) if mapping.credit_column else None
            if credit is not None and credit != 0:
                amount = abs(credit)
                direction = "inflow"
            elif debit is not None and debit != 0:
                amount = abs(debit)
                direction = "outflow"

        if amount is None and mapping.amount_column:
            signed = parse_flexible_decimal(row.get(mapping.amount_column))
            if signed is not None and signed != 0:
                direction = "inflow" if signed > 0 else "outflow"
                amount = abs(signed)

        if amount is None or amount <= 0:
            continue

        currency = default_currency.upper()
        if mapping.currency_column and row.get(mapping.currency_column):
            ccy = str(row[mapping.currency_column]).strip().upper()
            if len(ccy) == 3 and ccy.isalpha():
                currency = ccy

        parsed.append(
            ParsedTransactionRow(
                occurred_at=tx_date,
                amount=amount.quantize(Decimal("0.01")),
                currency=currency,
                direction=direction,
                merchant_raw=raw_desc[:255],
                merchant_clean=normalize_merchant_name(raw_desc)[:160],
                description=raw_desc,
                raw_payload={k: str(v) if v is not None else "" for k, v in row.items()},
            )
        )

    summary_text = f"Tabular {doc_type.upper()} statement with {len(parsed)} transactions."
    return parsed, summary_text
