"""Dedicated Bank of Georgia (საქართველოს ბანკი / BOG) Georgian PDF Statement Parser.

Supports:
- Native Bank of Georgia Internet Bank Georgian PDF exports (`ანგარიშიდან ამონაწერი`)
- Multi-page statements & multi-currency accounts (GEL, USD, EUR, GBP, etc.)
- Coordinate-aware pdfplumber extraction + robust text-based fallback
- Structured Georgian field parsing (ობიექტი, MCC, გადმომრიცხავი, მიმღები, დანიშნულება, საკომისიო)
- Deterministic MCC + Georgian merchant categorization hints
- Exact multi-currency opening/closing balance & inflow/outflow reconciliation (zero LLM tokens)
"""

from __future__ import annotations

import io
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.ai.parsers.tabular import ParsedTransactionRow

logger = logging.getLogger(__name__)

BOG_CURRENCIES = ("GEL", "USD", "EUR", "GBP", "CHF", "TRY", "RUB", "PLN", "AMD", "AZN")

# ISO 18245 MCC -> Financinio Default Category mapping
MCC_CATEGORY_MAP: dict[str, str] = {
    # Groceries & Supermarkets
    "5411": "Groceries",
    "5422": "Groceries",
    "5441": "Groceries",
    "5451": "Groceries",
    "5462": "Groceries",
    "5499": "Groceries",
    # Dining, Fast Food, Cafes, Bars
    "5811": "Dining & Coffee",
    "5812": "Dining & Coffee",
    "5813": "Dining & Coffee",
    "5814": "Dining & Coffee",
    # Transportation, Taxi, Transit, Fuel, Parking
    "4111": "Transportation & Transit",
    "4112": "Transportation & Transit",
    "4121": "Transportation & Transit",  # Taxicabs & Limousines (Yandex Go, Bolt)
    "4131": "Transportation & Transit",
    "4784": "Transportation & Transit",
    "5541": "Transportation & Transit",  # Service Stations / Fuel
    "5542": "Transportation & Transit",
    "7523": "Transportation & Transit",  # Parking
    # Utilities & Telecom
    "4812": "Utilities & Internet",
    "4814": "Utilities & Internet",
    "4816": "Utilities & Internet",
    "4899": "Utilities & Internet",
    "4900": "Utilities & Internet",
    # Healthcare & Pharmacies
    "5912": "Healthcare & Pharmacy",  # Drug Stores & Pharmacies (PSP, Aversi, GPC)
    "8011": "Healthcare & Pharmacy",
    "8021": "Healthcare & Pharmacy",
    "8041": "Healthcare & Pharmacy",
    "8042": "Healthcare & Pharmacy",
    "8043": "Healthcare & Pharmacy",
    "8049": "Healthcare & Pharmacy",
    "8062": "Healthcare & Pharmacy",
    "8071": "Healthcare & Pharmacy",
    "8099": "Healthcare & Pharmacy",
    # Software, Digital Goods & Subscriptions
    "5734": "Subscriptions & Software",
    "5815": "Subscriptions & Software",
    "5816": "Subscriptions & Software",
    "5817": "Subscriptions & Software",
    "5818": "Subscriptions & Software",
    "5968": "Subscriptions & Software",
    "7372": "Subscriptions & Software",
    # Shopping & Retail
    "5200": "Shopping & Retail",
    "5211": "Shopping & Retail",
    "5251": "Shopping & Retail",
    "5261": "Shopping & Retail",
    "5300": "Shopping & Retail",
    "5311": "Shopping & Retail",
    "5331": "Shopping & Retail",
    "5611": "Shopping & Retail",
    "5621": "Shopping & Retail",
    "5631": "Shopping & Retail",
    "5641": "Shopping & Retail",
    "5651": "Shopping & Retail",
    "5655": "Shopping & Retail",
    "5661": "Shopping & Retail",
    "5691": "Shopping & Retail",
    "5712": "Shopping & Retail",
    "5722": "Shopping & Retail",
    "5732": "Shopping & Retail",
    "5941": "Shopping & Retail",
    "5942": "Shopping & Retail",
    "5943": "Shopping & Retail",
    "5944": "Shopping & Retail",
    "5945": "Shopping & Retail",
    "5947": "Shopping & Retail",
    "5977": "Shopping & Retail",
    "5999": "Shopping & Retail",
    # Travel & Lodging
    "4511": "Travel & Lodging",
    "4722": "Travel & Lodging",
    "7011": "Travel & Lodging",
    "7512": "Travel & Lodging",
    # Entertainment & Fitness
    "7832": "Entertainment & Leisure",
    "7841": "Entertainment & Leisure",
    "7911": "Entertainment & Leisure",
    "7922": "Entertainment & Leisure",
    "7929": "Entertainment & Leisure",
    "7933": "Entertainment & Leisure",
    "7941": "Entertainment & Leisure",
    "7991": "Entertainment & Leisure",
    "7996": "Entertainment & Leisure",
    "7997": "Entertainment & Leisure",
    "7998": "Entertainment & Leisure",
    "7999": "Entertainment & Leisure",
    # Education
    "8211": "Education",
    "8220": "Education",
    "8241": "Education",
    "8244": "Education",
    "8249": "Education",
    "8299": "Education",
    # Financial / Transfers / ATM
    "4829": "Internal Transfer",
    "6010": "Internal Transfer",
    "6011": "Internal Transfer",
    "6012": "Internal Transfer",
    "6051": "Internal Transfer",
    "6536": "Internal Transfer",
    "6537": "Internal Transfer",
    "6538": "Internal Transfer",
    # Government, Taxes & Fines
    "9211": "Taxes & Fees",
    "9222": "Taxes & Fees",
    "9311": "Taxes & Fees",
    "9399": "Taxes & Fees",
}

# Georgian & local Georgia merchant/purpose keyword rules
BOG_GEORGIAN_KEYWORDS: list[tuple[tuple[str, ...], str, float]] = [
    (
        ("ხელფასი", "ანაზღაურება", "salary", "payroll", "სტიპენდია"),
        "Salary & Payroll",
        0.95,
    ),
    (
        (
            "მომსახურების საკომისიო",
            "ბანკის საკომისიო",
            "საკომისიო",
            "ჯარიმა",
            "სახელმწიფო ბაჟი",
            "გადასახადი",
            "service fee",
            "commission",
        ),
        "Taxes & Fees",
        0.94,
    ),
    (
        (
            "საკრედიტო ბარათზე გადარიცხვა",
            "პირადი გადარიცხვა",
            "საკუთარ ანგარიშზე",
            "ბარათიდან ბარათზე",
            "კონვერტაცია",
            "p2p",
        ),
        "Internal Transfer",
        0.92,
    ),
    (
        (
            "yandex go",
            "yandex",
            "bolt",
            "tbilisi transport",
            "ttc",
            "მეტრო",
            "wissol",
            "ვისოლი",
            "socar",
            "სოკარი",
            "gulf",
            "გალფი",
            "rompetrol",
            "რომპეტროლი",
            "lukoil",
            "ლუკოილი",
            "პარკინგ",
        ),
        "Transportation & Transit",
        0.93,
    ),
    (
        (
            "nikora",
            "ნიკორა",
            "spar",
            "სპარი",
            "ori nabiji",
            "ორი ნაბიჯი",
            "2 nabiji",
            "magniti",
            "მაგნიტი",
            "agrohub",
            "აგროჰაბ",
            "goodwill",
            "გუდვილ",
            "carrefour",
            "კარფურ",
            "fresco",
            "ფრესკო",
            "europroduct",
            "ევროპროდუქტ",
            "libre",
            "ლიბრე",
            "gastronome",
            "სუპერმარკეტ",
            "მარკეტ",
        ),
        "Groceries",
        0.92,
    ),
    (
        (
            "wolt",
            "glovo",
            "bolt food",
            "dunkin",
            "wendy",
            "kfc",
            "mcdonald",
            "entree",
            "paul",
            "საცხობ",
            "კაფე",
            "რესტორან",
            "ყავა",
            "coffee",
        ),
        "Dining & Coffee",
        0.92,
    ),
    (
        (
            "psp",
            "პსპ",
            "aversi",
            "ავერს",
            "gpc",
            "ჯიპისი",
            "pharmadepot",
            "ფარმადეპო",
            "აფთიაქ",
            "კლინიკა",
            "სამედიცინო",
        ),
        "Healthcare & Pharmacy",
        0.93,
    ),
    (
        (
            "magti",
            "მაგთი",
            "silknet",
            "სილქნეტ",
            "cellfie",
            "სელფი",
            "telasi",
            "თელასი",
            "tbilisi energy",
            "თბილისი ენერჯი",
            "gwp",
            "კომუნალურ",
            "ინტერნეტ",
            "მობილური",
        ),
        "Utilities & Internet",
        0.92,
    ),
    (
        (
            "zoommer",
            "ზუმერ",
            "alta",
            "ალტა",
            "gorgia",
            "გორგია",
            "domino",
            "დომინო",
            "veli.store",
            "extra.ge",
            "biblusi",
            "ბიბლუს",
            "zara",
            "lc waikiki",
            "dressup",
        ),
        "Shopping & Retail",
        0.90,
    ),
    (
        ("cavea", "კავეა", "tkt.ge", "biletebi", "oktopus", "snap fitness", "world class"),
        "Entertainment & Leisure",
        0.90,
    ),
    (
        ("wizz air", "georgian airways", "booking.com", "airbnb", "airalo"),
        "Travel & Lodging",
        0.90,
    ),
]

# Payment aggregator / corporate prefixes commonly found in BOG `ობიექტი:` strings
_AGGREGATOR_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:LTD|LLC|JSC|IE|S\.A\.|შპს|სს)\s+"
    r")?(?:"
    r"(?:KEEPZ\.ME|KEEPZ|PAYZE|FLITT|BOG|TBC\s*PAY|TBC|IPAY|UNIPAY|OPPA|TBCPAY|PAY\.GE|TNET)\s*\*\s*"
    r")",
    flags=re.IGNORECASE,
)
_CORP_PREFIX_RE = re.compile(
    r"^(?:LTD|LLC|JSC|შპს|სს|ი\.მ\.|ინდ\.მეწარმე)\s+", flags=re.IGNORECASE
)
_TRAILING_LOC_RE = re.compile(
    r"(?:,\s*|\s+)(?:Georgia|GEO|GE|Tbilisi|Batumi|Kutaisi|საქართველო|თბილისი)\.?$",
    flags=re.IGNORECASE,
)
_DATE_TOKEN_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_SIGNED_NUM_RE = re.compile(r"^[+-]?\d[\d,]*(?:\.\d+)?$")


@dataclass
class BogStatementMetadata:
    account_holder: str | None = None
    iban: str | None = None
    issue_date: str | None = None
    period: str | None = None
    card: str | None = None
    opening_balances: dict[str, Decimal] = field(default_factory=dict)
    closing_balances: dict[str, Decimal] = field(default_factory=dict)
    total_inflows: dict[str, Decimal] = field(default_factory=dict)
    total_outflows: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class BogRawEntry:
    occurred_at: date
    description: str
    amounts_by_currency: dict[str, Decimal] = field(default_factory=dict)
    trailing_signed_amount: Decimal | None = None


def is_bog_statement(text: str) -> bool:
    """Detect whether extracted PDF text comes from a Bank of Georgia (BOG) statement."""
    if not text:
        return False
    low = text.lower()
    if "საქართველოს ბანკი" in text or "bank of georgia" in low or "bagage22" in low:
        return True
    has_georgian_header = "ანგარიშიდან ამონაწერი" in text and (
        "დანიშნულება" in text or "საწყისი ნაშთი" in text
    )
    has_bog_iban = bool(re.search(r"\bGE\d{2}BG\d{16}\b", text))
    return has_georgian_header and has_bog_iban


def _parse_ddmmyyyy(token: str) -> date | None:
    m = _DATE_TOKEN_RE.match(token.strip())
    if not m:
        return None
    try:
        return datetime.strptime(token.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _parse_decimal_strict(token: str) -> Decimal | None:
    cleaned = token.strip().replace(",", "").replace(" ", "")
    if not cleaned or not _SIGNED_NUM_RE.match(cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _clean_bog_merchant(raw_obj: str) -> str:
    """Clean BOG POS merchant string (`ობიექტი:`), stripping aggregators & country suffixes."""
    s = re.sub(r"\s+", " ", raw_obj).strip(" ;,")
    # Strip aggregator prefixes like "LTD KEEPZ.ME*YANDEX GO" -> "YANDEX GO"
    s = _AGGREGATOR_PREFIX_RE.sub("", s).strip()
    # If there's still a prefix*merchant pattern like "KEEPZ*WOLT", take right side if meaningful
    if "*" in s:
        left, right = s.split("*", 1)
        if right.strip() and len(right.strip()) >= 2 and len(left.strip()) <= 20:
            s = right.strip()
    s = _CORP_PREFIX_RE.sub("", s).strip()
    # Remove trailing ", Georgia" / ", Tbilisi" repeatedly
    for _ in range(2):
        s = _TRAILING_LOC_RE.sub("", s).strip(" ,;-")
    # Title-case ALL-CAPS Latin merchant names (leave Georgian Unicode untouched)
    if s and s.isascii() and s.isupper() and len(s) > 3:
        s = s.title()
    return s or raw_obj.strip()


def _extract_bog_fields(description: str) -> dict[str, Any]:
    """Parse structured Georgian fields embedded inside a BOG `დანიშნულება` cell."""
    desc = re.sub(r"\s+", " ", description).strip()
    fields: dict[str, Any] = {"raw_description": desc}

    # Leading operation type before `-` (e.g., ჩარიცხვა, გადახდა, გადარიცხვა, კონვერტაცია)
    op_match = re.match(r"^([^\-;]+?)(?:\s*-\s*თანხა|\s*-\s*|$)", desc)
    if op_match:
        fields["operation_type"] = op_match.group(1).strip()

    # Inline posted amount & currency: "თანხა: GEL42.76" or "თანხა GEL1.00" or "თანხა: 42.76 GEL"
    amt_m = re.search(
        r"თანხა\s*:?\s*(GEL|USD|EUR|GBP|CHF|TRY|RUB|PLN|AMD|AZN)\s*([+-]?\d[\d,]*(?:\.\d{1,2})?)",
        desc,
        flags=re.IGNORECASE,
    )
    if not amt_m:
        amt_m = re.search(
            r"თანხა\s*:?\s*([+-]?\d[\d,]*(?:\.\d{1,2})?)\s*(GEL|USD|EUR|GBP|CHF|TRY|RUB|PLN|AMD|AZN)",
            desc,
            flags=re.IGNORECASE,
        )
        if amt_m:
            fields["inline_amount"] = _parse_decimal_strict(amt_m.group(1))
            fields["inline_currency"] = amt_m.group(2).upper()
    else:
        fields["inline_currency"] = amt_m.group(1).upper()
        fields["inline_amount"] = _parse_decimal_strict(amt_m.group(2))

    # Structured semicolon-delimited Georgian key/value attributes
    patterns = {
        "merchant_obj": r"ობიექტი\s*:\s*([^;]+)",
        "mcc": r"MCC\s*:\s*(\d{4})",
        "tx_timestamp": r"თარიღი\s*:\s*(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)",
        "card_last4": r"ბარათის\s*No\s*:\s*\*+(\d{4})",
        "sender": r"გადმომრიცხავი\s*:\s*([^;]+)",
        "recipient": r"მიმღები\s*:\s*([^;]+)",
        "purpose": r"დანიშნულება\s*:\s*([^;]+)",
        "original_op_amount": r"გადახდის ოპერაციის თანხა და ვალუტა\s*:\s*([^;]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, desc, flags=re.IGNORECASE)
        if m:
            fields[key] = m.group(1).strip(" ;,")

    return fields


def _suggest_bog_category(fields: dict[str, Any], direction: Literal["inflow", "outflow"]) -> tuple[str | None, float]:
    """Deterministically suggest a Financinio category from BOG MCC + Georgian keywords."""
    mcc = str(fields.get("mcc") or "").strip()
    if mcc:
        if mcc in MCC_CATEGORY_MAP:
            return MCC_CATEGORY_MAP[mcc], 0.96
        # Airlines MCC range 3000-3350, Car rental 3351-3500, Lodging 3501-3999
        if mcc.isdigit() and 3000 <= int(mcc) <= 3999:
            return "Travel & Lodging", 0.95

    searchable = " ".join(
        str(fields.get(k) or "")
        for k in ("merchant_obj", "purpose", "operation_type", "raw_description")
    ).lower()

    for keywords, category_name, conf in BOG_GEORGIAN_KEYWORDS:
        if any(kw in searchable for kw in keywords):
            return category_name, conf

    op_type = str(fields.get("operation_type") or "").lower()
    if "გადარიცხვა" in op_type:
        return "Internal Transfer", 0.88
    if "ჩარიცხვა" in op_type and direction == "inflow":
        if "პირადი" in searchable:
            return "Internal Transfer", 0.90
        return "Freelance & Side Income", 0.72

    return None, 0.50


def _build_bog_parsed_row(
    *,
    occurred_at: date,
    description: str,
    signed_amount: Decimal,
    currency: str,
) -> ParsedTransactionRow:
    fields = _extract_bog_fields(description)
    op_type = str(fields.get("operation_type") or "")
    direction: Literal["inflow", "outflow"] = "inflow" if signed_amount > 0 else "outflow"
    abs_amount = abs(signed_amount).quantize(Decimal("0.01"))

    # Determine human-readable merchant_clean and unique merchant_raw
    if fields.get("merchant_obj"):
        merchant_clean = _clean_bog_merchant(fields["merchant_obj"])
        ts = fields.get("tx_timestamp")
        # Include auth timestamp in merchant_raw so two identical-fare rides on same day don't collide
        merchant_raw = (
            f"{fields['merchant_obj']} [{ts}]" if ts else str(fields["merchant_obj"])
        )
    elif "საკომისიო" in description:
        # Extract fee text after first semicolon (e.g. "ანგარიშის მომსახურების საკომისიო")
        parts = [p.strip() for p in description.split(";") if p.strip()]
        fee_desc = parts[1].split(",")[0].strip() if len(parts) > 1 else "საბანკო საკომისიო"
        merchant_clean = f"BOG — {fee_desc}"
        merchant_raw = f"BOG {fee_desc}"
    elif fields.get("sender") or fields.get("recipient"):
        counterparty = str(fields.get("sender") or fields.get("recipient")).strip()
        purpose = str(fields.get("purpose") or "").strip()
        if purpose and purpose.lower() != counterparty.lower():
            merchant_clean = f"{counterparty} — {purpose}"
        elif op_type:
            merchant_clean = f"{counterparty} ({op_type})"
        else:
            merchant_clean = counterparty
        merchant_raw = f"{op_type}: {counterparty} | {purpose}".strip(" :|")
    else:
        # Clean fallback without the leading "გადახდა - თანხა: GEL1.00;"
        stripped = re.sub(
            r"^[^;]*თანხა\s*:?\s*(?:[A-Z]{3}\s*)?[\d,\.]+\s*(?:[A-Z]{3})?\s*;?\s*",
            "",
            description,
            flags=re.IGNORECASE,
        ).strip()
        merchant_clean = (stripped[:120] if stripped else description[:120]).strip()
        merchant_raw = merchant_clean

    cat_hint, conf_hint = _suggest_bog_category(fields, direction)

    # Compact, informative description preserving key Georgian metadata
    desc_parts: list[str] = []
    if op_type:
        desc_parts.append(op_type)
    if fields.get("purpose"):
        desc_parts.append(fields["purpose"])
    if fields.get("mcc"):
        desc_parts.append(f"MCC:{fields['mcc']}")
    if fields.get("tx_timestamp"):
        desc_parts.append(fields["tx_timestamp"])
    if fields.get("card_last4"):
        desc_parts.append(f"Card ****{fields['card_last4']}")
    if fields.get("original_op_amount"):
        desc_parts.append(f"Orig: {fields['original_op_amount']}")

    pretty_description = " · ".join(desc_parts) if desc_parts else description[:400]

    raw_payload: dict[str, Any] = {
        "bank": "bank_of_georgia",
        "operation_type": op_type or None,
        "mcc": fields.get("mcc"),
        "tx_timestamp": fields.get("tx_timestamp"),
        "card_last4": fields.get("card_last4"),
        "sender": fields.get("sender"),
        "recipient": fields.get("recipient"),
        "purpose": fields.get("purpose"),
        "original_op_amount": fields.get("original_op_amount"),
        "bog_category_hint": cat_hint,
        "bog_confidence_hint": conf_hint,
        "raw_description": description[:600],
    }

    return ParsedTransactionRow(
        occurred_at=occurred_at,
        amount=abs_amount,
        currency=currency.upper()[:3],
        direction=direction,
        merchant_raw=merchant_raw[:255],
        merchant_clean=merchant_clean[:160],
        description=pretty_description,
        raw_payload=raw_payload,
    )


def _extract_metadata_from_text(text: str, meta: BogStatementMetadata) -> None:
    m_holder = re.search(r"ანგარიშის მფლობელი\s*:\s*([^\n]+)", text)
    if m_holder and not meta.account_holder:
        meta.account_holder = m_holder.group(1).strip()

    m_iban = re.search(r"ანგარიშის ნომერი\s*:\s*(GE\d{2}BG\d{16})", text)
    if m_iban and not meta.iban:
        meta.iban = m_iban.group(1).strip()
    elif not meta.iban:
        m_any_iban = re.search(r"\b(GE\d{2}BG\d{16})\b", text)
        if m_any_iban:
            meta.iban = m_any_iban.group(1)

    m_issue = re.search(r"ამონაწერის გაცემის თარიღი\s*:\s*(\d{2}/\d{2}/\d{4})", text)
    if m_issue and not meta.issue_date:
        meta.issue_date = m_issue.group(1).strip()

    m_period = re.search(
        r"ამონაწერის პერიოდი\s*:\s*(\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4})", text
    )
    if m_period and not meta.period:
        meta.period = m_period.group(1).strip()

    m_card = re.search(r"ბარათი\s*:\s*([^\n]+)", text)
    if m_card and not meta.card:
        meta.card = m_card.group(1).strip()


def _group_words_into_lines(words: list[dict[str, Any]], y_tolerance: float = 3.5) -> list[list[dict[str, Any]]]:
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (round(float(w["top"]), 1), float(w["x0"])))
    lines: list[list[dict[str, Any]]] = []
    cur_line: list[dict[str, Any]] = [sorted_words[0]]
    cur_top = float(sorted_words[0]["top"])

    for w in sorted_words[1:]:
        top = float(w["top"])
        if abs(top - cur_top) <= y_tolerance:
            cur_line.append(w)
        else:
            cur_line.sort(key=lambda item: float(item["x0"]))
            lines.append(cur_line)
            cur_line = [w]
            cur_top = top
    if cur_line:
        cur_line.sort(key=lambda item: float(item["x0"]))
        lines.append(cur_line)
    return lines


def _nearest_currency_col(x_center: float, col_centers: dict[str, float]) -> str | None:
    if not col_centers:
        return None
    best_ccy = min(col_centers.keys(), key=lambda c: abs(col_centers[c] - x_center))
    if abs(col_centers[best_ccy] - x_center) <= 55.0:
        return best_ccy
    return None


def _extract_bog_via_pdfplumber(data: bytes) -> tuple[list[BogRawEntry], BogStatementMetadata, str]:
    """Coordinate-aware pdfplumber extractor tailored to Bank of Georgia's shaded PDF tables."""
    import pdfplumber

    meta = BogStatementMetadata()
    entries: list[BogRawEntry] = []
    page_texts: list[str] = []

    tx_col_centers: dict[str, float] = {}
    tx_first_ccy_x: float | None = None
    tx_desc_min_x: float = 80.0
    bal_col_centers: dict[str, float] = {}
    in_tx_table = False
    current_entry: BogRawEntry | None = None

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            raw_page_text = page.extract_text() or ""
            if raw_page_text.strip():
                page_texts.append(raw_page_text.strip())

            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            lines = _group_words_into_lines(words, y_tolerance=3.5)

            for line in lines:
                line_text = " ".join(w["text"] for w in line).strip()
                if not line_text:
                    continue

                # Skip page footers / stamp / confidentiality marker
                if (
                    re.search(r"გვ\.\s*\d+\s*\(სულ", line_text)
                    or "კონფიდენციალური" in line_text
                    or "PRINTED FROM INTERNET BANK" in line_text.upper()
                    or 'J.S.C "BANK OF GEORGIA"' in line_text.upper()
                ):
                    continue

                # Detect currency column headers (either Balance Summary or Transactions table)
                ccy_words = [w for w in line if w["text"].upper() in BOG_CURRENCIES]
                if len(ccy_words) >= 2:
                    centers = {
                        w["text"].upper(): (float(w["x0"]) + float(w["x1"])) / 2.0
                        for w in ccy_words
                    }
                    if "თარიღი" in line_text or "დანიშნულება" in line_text:
                        tx_col_centers = centers
                        tx_first_ccy_x = min(float(w["x0"]) for w in ccy_words)
                        desc_word = next((w for w in line if "დანიშნულება" in w["text"]), None)
                        if desc_word is not None:
                            tx_desc_min_x = float(desc_word["x0"]) - 8.0
                        in_tx_table = True
                        continue
                    else:
                        bal_col_centers = centers
                        continue

                # Opening / Closing balance rows
                if "საწყისი ნაშთი" in line_text or "საბოლოო ნაშთი" in line_text:
                    target = (
                        meta.opening_balances
                        if "საწყისი ნაშთი" in line_text
                        else meta.closing_balances
                    )
                    cols = bal_col_centers or tx_col_centers
                    if cols:
                        min_ccy_x = min(cols.values()) - 35.0
                        for w in line:
                            xc = (float(w["x0"]) + float(w["x1"])) / 2.0
                            if xc >= min_ccy_x:
                                val = _parse_decimal_strict(w["text"])
                                if val is not None:
                                    ccy = _nearest_currency_col(xc, cols)
                                    if ccy:
                                        target[ccy] = val
                    continue

                # Footer totals rows -> end of transactions table
                if "შემოსული თანხების ჯამი" in line_text or "გასული თანხების ჯამი" in line_text:
                    if current_entry is not None:
                        entries.append(current_entry)
                        current_entry = None
                    in_tx_table = False
                    target = (
                        meta.total_inflows
                        if "შემოსული" in line_text
                        else meta.total_outflows
                    )
                    cols = tx_col_centers or bal_col_centers
                    if cols:
                        min_ccy_x = min(cols.values()) - 35.0
                        for w in line:
                            xc = (float(w["x0"]) + float(w["x1"])) / 2.0
                            if xc >= min_ccy_x:
                                val = _parse_decimal_strict(w["text"])
                                if val is not None:
                                    ccy = _nearest_currency_col(xc, cols)
                                    if ccy:
                                        target[ccy] = abs(val)
                    continue

                if not in_tx_table or tx_first_ccy_x is None:
                    continue

                # Inside Transactions Table: check if line starts a new transaction row
                first_word = line[0]
                maybe_date = (
                    _parse_ddmmyyyy(first_word["text"])
                    if float(first_word["x0"]) < tx_desc_min_x
                    else None
                )

                if maybe_date is not None:
                    if current_entry is not None:
                        entries.append(current_entry)
                    current_entry = BogRawEntry(occurred_at=maybe_date, description="")
                    body_words = line[1:]
                else:
                    if current_entry is None:
                        continue
                    body_words = line

                desc_tokens: list[str] = []
                for w in body_words:
                    x0 = float(w["x0"])
                    xc = (x0 + float(w["x1"])) / 2.0
                    if x0 >= tx_first_ccy_x - 14.0:
                        val = _parse_decimal_strict(w["text"])
                        if val is not None:
                            ccy = _nearest_currency_col(xc, tx_col_centers)
                            if ccy and val != 0:
                                current_entry.amounts_by_currency[ccy] = val
                            continue
                    desc_tokens.append(w["text"])

                if desc_tokens:
                    chunk = " ".join(desc_tokens).strip()
                    current_entry.description = (
                        f"{current_entry.description} {chunk}".strip()
                        if current_entry.description
                        else chunk
                    )

    if current_entry is not None:
        entries.append(current_entry)

    full_text = "\n\n--- PAGE BREAK ---\n\n".join(page_texts)
    _extract_metadata_from_text(full_text, meta)
    return entries, meta, full_text


def _parse_balances_from_text(text: str, meta: BogStatementMetadata) -> None:
    """Parse opening/closing balances and totals from raw OCR/pypdf text (horizontal or stacked)."""
    # 1. Horizontal balance lines: e.g. "16/11/2026 საწყისი ნაშთი: 9.35 1.17 0 0.00"
    header_ccys: list[str] = []
    for line in text.splitlines():
        tokens = [t.strip().upper() for t in line.split() if t.strip().upper() in BOG_CURRENCIES]
        if len(tokens) >= 2:
            header_ccys = tokens
            break

    for label, target in (
        ("საწყისი ნაშთი", meta.opening_balances),
        ("საბოლოო ნაშთი", meta.closing_balances),
        ("შემოსული თანხების ჯამი", meta.total_inflows),
        ("გასული თანხების ჯამი", meta.total_outflows),
    ):
        if target:
            continue
        m = re.search(rf"{label}\s*:?\s*([^\n]+)", text)
        if m and header_ccys:
            nums = [
                d
                for tok in m.group(1).split()
                if (d := _parse_decimal_strict(tok)) is not None
            ]
            if len(nums) >= 1:
                for ccy, val in zip(header_ccys, nums, strict=False):
                    target[ccy] = abs(val) if "ჯამი" in label else val

    # 2. Stacked OCR/pypdf format (e.g. "GEL\n9.35\n3.71\nUSD\n1.17\n1.17")
    if not meta.opening_balances and not meta.closing_balances:
        m_tx_hdr = re.search(r"თარიღი\s+დანიშნულება", text)
        bal_block = text[: m_tx_hdr.start()] if m_tx_hdr else text[:1500]
        if "საწყისი ნაშთი" in bal_block and "საბოლოო ნაშთი" in bal_block:
            stacked_re = re.compile(
                r"\b(GEL|USD|EUR|GBP|CHF|TRY|RUB)\s*\n\s*([+-]?\d[\d,]*(?:\.\d+)?)\s*\n\s*([+-]?\d[\d,]*(?:\.\d+)?)"
            )
            for m in stacked_re.finditer(bal_block):
                ccy = m.group(1).upper()
                v1 = _parse_decimal_strict(m.group(2))
                v2 = _parse_decimal_strict(m.group(3))
                if v1 is not None and v2 is not None:
                    meta.opening_balances[ccy] = v1
                    meta.closing_balances[ccy] = v2


def parse_bog_text(
    text: str,
    default_currency: str = "GEL",
) -> tuple[list[ParsedTransactionRow], BogStatementMetadata]:
    """Fallback text-based BOG Georgian statement parser (handles pypdf & OCR text)."""
    meta = BogStatementMetadata()
    _extract_metadata_from_text(text, meta)
    _parse_balances_from_text(text, meta)

    # Locate the transaction table section
    start_idx = 0
    m_hdr = re.search(r"თარიღი\s+დანიშნულება[^\n]*\n", text)
    if m_hdr:
        start_idx = m_hdr.end()

    end_markers = [
        text.find("შემოსული თანხების ჯამი", start_idx),
        text.find("გასული თანხების ჯამი", start_idx),
    ]
    valid_ends = [idx for idx in end_markers if idx > start_idx]
    end_idx = min(valid_ends) if valid_ends else len(text)
    tx_block = text[start_idx:end_idx]

    raw_entries: list[BogRawEntry] = []
    cur: BogRawEntry | None = None

    for raw_line in tx_block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if (
            re.search(r"გვ\.\s*\d+\s*\(სულ", line)
            or "კონფიდენციალური" in line
            or "თარიღი დანიშნულება" in line
            or "--- PAGE BREAK ---" in line
        ):
            continue

        # Check if line starts with DD/MM/YYYY followed by description
        m_row = re.match(r"^(\d{2}/\d{2}/\d{4})\s+(.+)$", line)
        if m_row:
            tx_date = _parse_ddmmyyyy(m_row.group(1))
            if tx_date is not None:
                if cur is not None:
                    raw_entries.append(cur)
                rest = m_row.group(2).strip()
                # Check if line ends with a signed column amount (e.g. "... -4.8")
                trailing_amt: Decimal | None = None
                m_tail = re.search(r"\s+([+-]?\d[\d,]*(?:\.\d+)?)$", rest)
                if m_tail:
                    cand = _parse_decimal_strict(m_tail.group(1))
                    # Guard against matching a 4-digit card number or MCC code without decimal/sign
                    if cand is not None and (
                        "." in m_tail.group(1) or m_tail.group(1).startswith(("-", "+"))
                    ):
                        trailing_amt = cand
                        rest = rest[: m_tail.start()].strip()
                cur = BogRawEntry(
                    occurred_at=tx_date,
                    description=rest,
                    trailing_signed_amount=trailing_amt,
                )
                continue

        if cur is None:
            continue

        # Standalone signed amount line (exactly how pypdf/OCR outputs BOG amount columns!)
        standalone = _parse_decimal_strict(line)
        if standalone is not None:
            cur.trailing_signed_amount = standalone
            continue

        # Continuation of wrapped Georgian description
        m_tail = re.search(r"\s+([+-]?\d[\d,]*(?:\.\d+)?)$", line)
        if m_tail and ("." in m_tail.group(1) or m_tail.group(1).startswith(("-", "+"))):
            cand = _parse_decimal_strict(m_tail.group(1))
            if cand is not None and not re.search(r"(GEL|USD|EUR|GBP)$", line, flags=re.IGNORECASE):
                cur.trailing_signed_amount = cand
                line = line[: m_tail.start()].strip()

        cur.description = f"{cur.description} {line}".strip()

    if cur is not None:
        raw_entries.append(cur)

    rows: list[ParsedTransactionRow] = []
    for entry in raw_entries:
        fields = _extract_bog_fields(entry.description)
        ccy = str(fields.get("inline_currency") or default_currency or "GEL").upper()
        signed = entry.trailing_signed_amount
        if signed is None:
            inline_amt = fields.get("inline_amount")
            if inline_amt is None or inline_amt == 0:
                continue
            op_low = str(fields.get("operation_type") or "").lower()
            is_inflow = any(
                k in op_low for k in ("ჩარიცხვა", "დაბრუნება", "შეტანა", "შევსება", "ქეშბექ")
            )
            signed = abs(inline_amt) if is_inflow else -abs(inline_amt)

        if signed == 0:
            continue

        rows.append(
            _build_bog_parsed_row(
                occurred_at=entry.occurred_at,
                description=entry.description,
                signed_amount=signed,
                currency=ccy,
            )
        )

    return rows, meta


def _reconcile_bog_statement(
    rows: list[ParsedTransactionRow],
    meta: BogStatementMetadata,
) -> tuple[bool | None, str]:
    """Verify multi-currency opening + net == closing balances on Bank of Georgia statements."""
    inflows_by_ccy: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    outflows_by_ccy: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for r in rows:
        if r.direction == "inflow":
            inflows_by_ccy[r.currency] += r.amount
        else:
            outflows_by_ccy[r.currency] += r.amount

    header_bits: list[str] = ["Bank of Georgia (BOG)"]
    if meta.period:
        header_bits.append(meta.period)
    if meta.iban:
        header_bits.append(f"IBAN ...{meta.iban[-4:]}")
    prefix = " · ".join(header_bits)

    checked_currencies = [
        ccy
        for ccy in BOG_CURRENCIES
        if ccy in meta.opening_balances and ccy in meta.closing_balances
    ]

    if not checked_currencies:
        return (
            None,
            f"{prefix}: parsed {len(rows)} transactions (opening/closing balance summary not detected).",
        )

    all_ok = True
    parts: list[str] = []
    for ccy in checked_currencies:
        opening = meta.opening_balances[ccy]
        closing = meta.closing_balances[ccy]
        net = inflows_by_ccy[ccy] - outflows_by_ccy[ccy]
        expected = opening + net
        diff = abs(expected - closing)
        # Skip silent 0.00 -> 0.00 unused currency columns to keep the note concise
        if opening == 0 and closing == 0 and net == 0:
            continue
        if diff <= Decimal("0.05"):
            sign_net = f"+{net:.2f}" if net >= 0 else f"{net:.2f}"
            parts.append(f"{ccy} {opening:.2f} ({sign_net}) = {closing:.2f} ✓")
        else:
            all_ok = False
            parts.append(
                f"{ccy} mismatch: expected {expected:.2f} vs statement {closing:.2f} (diff {diff:.2f})"
            )

    summary = " · ".join(parts) if parts else "balances verified"
    status_word = "verified" if all_ok else "reconciliation warning"
    note = f"{prefix} {status_word}: {summary} ({len(rows)} transactions)."
    return all_ok, note


def parse_bog_pdf(
    data: bytes,
    *,
    default_currency: str = "GEL",
    strict: bool = False,
) -> tuple[list[ParsedTransactionRow], str, bool | None, str]:
    """Parse a Bank of Georgia (BOG) Georgian PDF statement deterministically (0 LLM tokens).

    Returns:
        (parsed_rows, extracted_text, balance_reconciled, reconciliation_note)
    """
    entries: list[BogRawEntry] = []
    meta = BogStatementMetadata()
    extracted_text = ""

    try:
        entries, meta, extracted_text = _extract_bog_via_pdfplumber(data)
    except Exception as exc:
        logger.warning("pdfplumber BOG extraction failed, falling back to pypdf text: %s", exc)

    if not extracted_text:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            extracted_text = "\n\n--- PAGE BREAK ---\n\n".join(
                (p.extract_text() or "").strip() for p in reader.pages if (p.extract_text() or "").strip()
            )
        except Exception as exc:
            logger.warning("pypdf BOG text extraction failed: %s", exc)

    if strict and not is_bog_statement(extracted_text):
        raise ValueError(
            "This file does not look like a Bank of Georgia (საქართველოს ბანკი) PDF statement. "
            "Export your statement PDF from BOG Internet Bank (ანგარიშიდან ამონაწერი) or use the General Statement upload."
        )

    rows: list[ParsedTransactionRow] = []

    if entries:
        for entry in entries:
            if entry.amounts_by_currency:
                for ccy, signed_amt in entry.amounts_by_currency.items():
                    if signed_amt == 0:
                        continue
                    rows.append(
                        _build_bog_parsed_row(
                            occurred_at=entry.occurred_at,
                            description=entry.description,
                            signed_amount=signed_amt,
                            currency=ccy,
                        )
                    )
            else:
                # Row had date & description but amount didn't align into a currency column -> infer from text
                fields = _extract_bog_fields(entry.description)
                inline_amt = fields.get("inline_amount")
                ccy = str(fields.get("inline_currency") or default_currency or "GEL").upper()
                if inline_amt is not None and inline_amt != 0:
                    op_low = str(fields.get("operation_type") or "").lower()
                    is_inflow = any(
                        k in op_low for k in ("ჩარიცხვა", "დაბრუნება", "შეტანა", "შევსება", "ქეშბექ")
                    )
                    signed_amt = abs(inline_amt) if is_inflow else -abs(inline_amt)
                    rows.append(
                        _build_bog_parsed_row(
                            occurred_at=entry.occurred_at,
                            description=entry.description,
                            signed_amount=signed_amt,
                            currency=ccy,
                        )
                    )

    # If coordinate extraction produced 0 rows (e.g., OCR-wrapped or borderless PDF), run text fallback
    if not rows and extracted_text:
        rows, text_meta = parse_bog_text(extracted_text, default_currency=default_currency)
        if not meta.opening_balances and text_meta.opening_balances:
            meta.opening_balances = text_meta.opening_balances
        if not meta.closing_balances and text_meta.closing_balances:
            meta.closing_balances = text_meta.closing_balances
        if not meta.period and text_meta.period:
            meta.period = text_meta.period
        if not meta.iban and text_meta.iban:
            meta.iban = text_meta.iban

    reconciled, note = _reconcile_bog_statement(rows, meta)
    return rows, extracted_text, reconciled, note
