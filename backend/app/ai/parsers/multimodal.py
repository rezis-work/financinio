import base64
import io
from datetime import date
from decimal import Decimal
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.ai.parsers.tabular import (
    ParsedTransactionRow,
    parse_flexible_date,
    parse_flexible_decimal,
)
from app.services.ledger_service import normalize_merchant_name


class ExtractedTransactionItem(BaseModel):
    occurred_at: str = Field(description="ISO date YYYY-MM-DD")
    merchant: str = Field(description="Merchant or payee name")
    description: str | None = Field(default=None, description="Full transaction memo or line items")
    amount: float = Field(gt=0, description="Positive transaction amount")
    currency: str | None = Field(default=None, description="3-letter ISO currency code if shown")
    direction: Literal["inflow", "outflow"] = Field(
        description="'inflow' for deposits/credits/refunds, 'outflow' for purchases/debits/charges"
    )


class ExtractedDocumentPayload(BaseModel):
    opening_balance: float | None = Field(default=None, description="Statement opening balance if present")
    closing_balance: float | None = Field(default=None, description="Statement closing balance if present")
    transactions: list[ExtractedTransactionItem] = Field(default_factory=list)
    summary_text: str = Field(
        default="", description="Plain-text summary of receipt/statement for semantic search"
    )


def extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())
    return "\n\n--- PAGE BREAK ---\n\n".join(pages)


async def parse_multimodal_document(
    *,
    data: bytes,
    mime_type: str,
    doc_type: Literal["pdf_statement", "receipt"],
    default_currency: str,
    llm: BaseChatModel | None,
) -> tuple[list[ParsedTransactionRow], str, bool | None, str | None]:
    """Extract structured transactions from PDF statements or receipt images via LangChain."""
    extracted_text = ""
    if mime_type == "application/pdf" or doc_type == "pdf_statement":
        try:
            extracted_text = extract_pdf_text(data)
        except Exception:
            extracted_text = ""

    if llm is None:
        raise ValueError(
            "An LLM API key (GOOGLE_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY) is required "
            "to parse PDF statements and receipt images. Configure your .env or upload a CSV/Excel file."
        )

    structured_llm = llm.with_structured_output(ExtractedDocumentPayload)

    instruction = (
        "You are a precision financial document parser. Extract every transaction accurately. "
        "For receipts, return one transaction representing the receipt total (with line items in description). "
        "For bank/credit card statements, extract every posted transaction plus opening and closing balances if shown. "
        f"Use {default_currency} if no currency is explicitly specified. Return ISO dates (YYYY-MM-DD)."
    )

    if extracted_text and len(extracted_text.strip()) > 80:
        msg = HumanMessage(content=f"{instruction}\n\nDocument text:\n{extracted_text[:40000]}")
    else:
        b64 = base64.b64encode(data).decode("ascii")
        media_mime = mime_type if mime_type.startswith("image/") else "image/png"
        msg = HumanMessage(
            content=[
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": f"data:{media_mime};base64,{b64}"}},
            ]
        )

    result: ExtractedDocumentPayload = await structured_llm.ainvoke([msg])  # type: ignore[assignment]

    rows: list[ParsedTransactionRow] = []
    for item in result.transactions:
        tx_date = parse_flexible_date(item.occurred_at) or date.today()
        amount = parse_flexible_decimal(item.amount)
        if amount is None or amount <= 0:
            continue
        ccy = (item.currency or default_currency).upper()[:3]
        rows.append(
            ParsedTransactionRow(
                occurred_at=tx_date,
                amount=abs(amount).quantize(Decimal("0.01")),
                currency=ccy,
                direction=item.direction,
                merchant_raw=item.merchant[:255],
                merchant_clean=normalize_merchant_name(item.merchant)[:160],
                description=item.description or item.merchant,
                raw_payload=item.model_dump(),
            )
        )

    # Balance reconciliation check for statements
    reconciled: bool | None = None
    reconciliation_note: str | None = None
    if result.opening_balance is not None and result.closing_balance is not None:
        opening = Decimal(str(result.opening_balance))
        closing = Decimal(str(result.closing_balance))
        net_delta = sum(
            (r.amount if r.direction == "inflow" else -r.amount for r in rows),
            Decimal("0.00"),
        )
        expected_closing = opening + net_delta
        diff = abs(expected_closing - closing)
        reconciled = diff <= Decimal("0.05")
        if reconciled:
            reconciliation_note = (
                f"Statement balanced: opening {opening:.2f} + net {net_delta:.2f} = {closing:.2f}."
            )
        else:
            reconciliation_note = (
                f"Balance mismatch of {diff:.2f}: expected {expected_closing:.2f} vs "
                f"statement closing {closing:.2f}. Please review extracted rows."
            )

    full_text = extracted_text or result.summary_text
    return rows, full_text, reconciled, reconciliation_note
