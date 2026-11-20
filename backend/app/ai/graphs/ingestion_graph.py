import base64
import logging
import re
from decimal import Decimal
from typing import Any, Literal, TypedDict
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.ai.llm_factory import get_chat_model
from app.ai.observability import redact_pii
from app.ai.parsers.multimodal import parse_multimodal_document
from app.ai.parsers.tabular import parse_tabular_statement
from app.services.ledger_service import compute_transaction_fingerprint
from app.services.vector_service import VectorMemoryBackend, get_vector_service

logger = logging.getLogger(__name__)


class StagedRowDict(TypedDict, total=False):
    row_index: int
    occurred_at: str  # ISO date YYYY-MM-DD
    amount: str  # Decimal string
    currency: str
    direction: Literal["inflow", "outflow"]
    merchant_raw: str
    merchant_clean: str
    description: str | None
    suggested_category_id: str | None
    suggested_category_name: str | None
    confidence: float
    categorization_source: str
    fingerprint: str
    is_duplicate: bool
    needs_review: bool
    user_approved: bool
    raw_payload: dict[str, Any]


class IngestionState(TypedDict, total=False):
    user_id: str
    account_id: str
    account_currency: str
    document_id: str
    batch_id: str
    filename: str
    mime_type: str
    doc_type: Literal["csv", "xlsx", "pdf_statement", "receipt"]
    file_bytes_b64: str
    categories: list[dict[str, str]]  # [{id, name, kind}]
    rules: list[dict[str, Any]]  # [{match_pattern, match_type, category_id, merchant_override}]
    existing_fingerprints: list[str]
    extracted_text: str
    balance_reconciled: bool | None
    reconciliation_note: str | None
    staged_rows: list[StagedRowDict]
    approved_rows: list[StagedRowDict]
    learning_examples: list[dict[str, str]]


class CategorizedItem(BaseModel):
    row_index: int
    merchant_clean: str = Field(description="Clean human-friendly merchant name")
    category_name: str = Field(description="Exact category name from the provided list")
    confidence: float = Field(ge=0.0, le=1.0)


class BatchCategorizationOutput(BaseModel):
    items: list[CategorizedItem] = Field(default_factory=list)


_KEYWORD_HEURISTICS: list[tuple[tuple[str, ...], str]] = [
    (("salary", "payroll", "direct deposit", "paycheck", "gusto", "adp"), "Salary & Payroll"),
    (("whole foods", "trader joe", "kroger", "aldi", "costco", "grocery", "market", "supermarket", "carrefour"), "Groceries"),
    (("starbucks", "coffee", "cafe", "mcdonald", "chipotle", "uber eats", "doordash", "restaurant", "pizza", "burger", "wolt", "glovo"), "Dining & Coffee"),
    (("uber", "lyft", "bolt", "metro", "subway", "shell", "chevron", "exxon", "gas", "fuel", "parking", "transit"), "Transportation & Transit"),
    (("netflix", "spotify", "apple.com/bill", "openai", "claude", "github", "notion", "icloud", "youtube", "hulu", "adobe"), "Subscriptions & Software"),
    (("amazon", "amzn", "target", "walmart", "ikea", "apple store", "zara", "nike", "best buy"), "Shopping & Retail"),
    (("rent", "mortgage", "apartment", "hoa", "landlord"), "Housing & Rent"),
    (("electric", "water", "internet", "comcast", "verizon", "at&t", "t-mobile", "utility", "coned"), "Utilities & Internet"),
    (("pharmacy", "cvs", "walgreens", "hospital", "clinic", "dental", "doctor", "health"), "Healthcare & Pharmacy"),
    (("airbnb", "hotel", "delta", "united", "american airlines", "booking.com", "expedia", "flight"), "Travel & Lodging"),
    (("transfer", "zelle", "venmo", "wise", "revolut"), "Internal Transfer"),
]


def _match_user_rule(merchant_text: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = merchant_text.lower()
    for rule in rules:
        pattern = str(rule.get("match_pattern", ""))
        match_type = rule.get("match_type", "contains")
        if not pattern:
            continue
        if match_type == "exact" and lowered == pattern.lower():
            return rule
        if match_type == "contains" and pattern.lower() in lowered:
            return rule
        if match_type == "regex":
            try:
                if re.search(pattern, merchant_text, flags=re.IGNORECASE):
                    return rule
            except re.error:
                continue
    return None


def _heuristic_categorize(
    merchant_text: str,
    direction: str,
    categories_by_lower: dict[str, dict[str, str]],
) -> tuple[dict[str, str] | None, float]:
    lowered = merchant_text.lower()
    for keywords, target_name in _KEYWORD_HEURISTICS:
        if any(kw in lowered for kw in keywords):
            cat = categories_by_lower.get(target_name.lower())
            if cat:
                return cat, 0.78
    if direction == "inflow":
        cat = categories_by_lower.get("salary & payroll") or categories_by_lower.get(
            "freelance & side income"
        )
        if cat:
            return cat, 0.55
    uncat = categories_by_lower.get("uncategorized")
    return uncat, 0.40


def build_ingestion_graph(
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    llm_fast: BaseChatModel | None = None,
    llm_vision: BaseChatModel | None = None,
    vector_service: VectorMemoryBackend | None = None,
):
    """Compile the LangGraph Document Ingestion & HITL Review workflow."""

    async def parse_document_node(state: IngestionState) -> dict[str, Any]:
        raw_bytes = base64.b64decode(state["file_bytes_b64"])
        doc_type = state["doc_type"]
        default_ccy = state.get("account_currency", "USD")

        fast_model = llm_fast if llm_fast is not None else get_chat_model("fast")
        vision_model = llm_vision if llm_vision is not None else get_chat_model("vision")

        reconciled: bool | None = None
        reconciliation_note: str | None = None

        if doc_type in ("csv", "xlsx"):
            parsed_rows, extracted_text = await parse_tabular_statement(
                data=raw_bytes,
                doc_type=doc_type,
                default_currency=default_ccy,
                llm=fast_model,
            )
            reconciled = True
            reconciliation_note = f"Parsed {len(parsed_rows)} rows from {doc_type.upper()}."
        else:
            parsed_rows, extracted_text, reconciled, reconciliation_note = (
                await parse_multimodal_document(
                    data=raw_bytes,
                    mime_type=state.get("mime_type", "application/pdf"),
                    doc_type=doc_type,
                    default_currency=default_ccy,
                    llm=vision_model,
                )
            )

        staged: list[StagedRowDict] = []
        for idx, row in enumerate(parsed_rows):
            staged.append(
                StagedRowDict(
                    row_index=idx,
                    occurred_at=row.occurred_at.isoformat(),
                    amount=f"{row.amount:.2f}",
                    currency=row.currency,
                    direction=row.direction,
                    merchant_raw=row.merchant_raw,
                    merchant_clean=row.merchant_clean,
                    description=row.description,
                    suggested_category_id=None,
                    suggested_category_name=None,
                    confidence=0.5,
                    categorization_source="heuristic",
                    fingerprint="",
                    is_duplicate=False,
                    needs_review=True,
                    user_approved=True,
                    raw_payload=row.raw_payload,
                )
            )

        return {
            "staged_rows": staged,
            "extracted_text": redact_pii(extracted_text),
            "balance_reconciled": reconciled,
            "reconciliation_note": reconciliation_note,
            # Clear raw bytes from checkpointed state once parsed to keep checkpoints lean
            "file_bytes_b64": "",
        }

    async def dedupe_transactions_node(state: IngestionState) -> dict[str, Any]:
        account_uuid = UUID(state["account_id"])
        seen = set(state.get("existing_fingerprints", []))
        updated: list[StagedRowDict] = []

        for row in state.get("staged_rows", []):
            from datetime import date

            fp = compute_transaction_fingerprint(
                account_id=account_uuid,
                occurred_at=date.fromisoformat(row["occurred_at"]),
                amount=Decimal(row["amount"]),
                direction=row["direction"],
                merchant_raw=row["merchant_raw"],
            )
            is_dup = fp in seen
            seen.add(fp)
            new_row = dict(row)
            new_row["fingerprint"] = fp
            new_row["is_duplicate"] = is_dup
            if is_dup:
                new_row["user_approved"] = False
            updated.append(new_row)  # type: ignore[arg-type]

        return {"staged_rows": updated}

    async def categorize_transactions_node(state: IngestionState) -> dict[str, Any]:
        user_uuid = UUID(state["user_id"])
        categories = state.get("categories", [])
        categories_by_id = {c["id"]: c for c in categories}
        categories_by_lower = {c["name"].lower(): c for c in categories}
        rules = state.get("rules", [])
        vec = vector_service if vector_service is not None else get_vector_service()
        fast_model = llm_fast if llm_fast is not None else get_chat_model("fast")

        rows = [dict(r) for r in state.get("staged_rows", [])]
        llm_pending_indices: list[int] = []

        # Tier 1 (User Rules) & Tier 2 (Upstash Vector Merchant Memory)
        for idx, row in enumerate(rows):
            search_text = f"{row['merchant_raw']} {row.get('description') or ''}".strip()

            rule = _match_user_rule(search_text, rules)
            if rule and rule.get("category_id") in categories_by_id:
                cat = categories_by_id[rule["category_id"]]
                row["suggested_category_id"] = cat["id"]
                row["suggested_category_name"] = cat["name"]
                if rule.get("merchant_override"):
                    row["merchant_clean"] = rule["merchant_override"]
                row["confidence"] = 0.99
                row["categorization_source"] = "rule"
                row["needs_review"] = bool(row["is_duplicate"])
                continue

            mem_match = await vec.lookup_merchant_memory(user_uuid, search_text, min_score=0.85)
            if mem_match and mem_match.category_id in categories_by_id:
                cat = categories_by_id[mem_match.category_id]
                row["suggested_category_id"] = cat["id"]
                row["suggested_category_name"] = cat["name"]
                if mem_match.merchant_clean:
                    row["merchant_clean"] = mem_match.merchant_clean
                row["confidence"] = round(min(mem_match.score, 0.98), 3)
                row["categorization_source"] = "vector"
                row["needs_review"] = bool(row["is_duplicate"] or mem_match.score < 0.90)
                continue

            llm_pending_indices.append(idx)

        # Tier 3: Batched LangChain Structured Output (or Heuristic fallback if no LLM key)
        if llm_pending_indices and fast_model is not None and categories:
            structured_llm = fast_model.with_structured_output(BatchCategorizationOutput)
            cat_list_str = ", ".join(f"{c['name']} ({c['kind']})" for c in categories)

            for chunk_start in range(0, len(llm_pending_indices), 25):
                chunk_indices = llm_pending_indices[chunk_start : chunk_start + 25]
                lines = [
                    f"- row_index={i}: date={rows[i]['occurred_at']} | dir={rows[i]['direction']} | "
                    f"amount={rows[i]['amount']} {rows[i]['currency']} | raw={redact_pii(rows[i]['merchant_raw'])}"
                    for i in chunk_indices
                ]
                prompt = (
                    "Normalize each merchant name and assign the single best category from the allowed list.\n"
                    f"Allowed categories: {cat_list_str}\n\n"
                    "Transactions:\n" + "\n".join(lines)
                )
                try:
                    batch_out: BatchCategorizationOutput = await structured_llm.ainvoke(prompt)  # type: ignore[assignment]
                    by_idx = {item.row_index: item for item in batch_out.items}
                    for i in chunk_indices:
                        item = by_idx.get(i)
                        if item:
                            cat = categories_by_lower.get(item.category_name.lower())
                            rows[i]["merchant_clean"] = item.merchant_clean[:160]
                            rows[i]["suggested_category_id"] = cat["id"] if cat else None
                            rows[i]["suggested_category_name"] = cat["name"] if cat else None
                            rows[i]["confidence"] = round(float(item.confidence), 3)
                            rows[i]["categorization_source"] = "llm"
                            rows[i]["needs_review"] = bool(
                                rows[i]["is_duplicate"] or item.confidence < 0.85 or cat is None
                            )
                except Exception as exc:
                    logger.warning("LLM batch categorization failed, using heuristic: %s", exc)
                    for i in chunk_indices:
                        cat, conf = _heuristic_categorize(
                            rows[i]["merchant_raw"], rows[i]["direction"], categories_by_lower
                        )
                        rows[i]["suggested_category_id"] = cat["id"] if cat else None
                        rows[i]["suggested_category_name"] = cat["name"] if cat else None
                        rows[i]["confidence"] = conf
                        rows[i]["categorization_source"] = "heuristic"
                        rows[i]["needs_review"] = True
        else:
            for i in llm_pending_indices:
                cat, conf = _heuristic_categorize(
                    rows[i]["merchant_raw"], rows[i]["direction"], categories_by_lower
                )
                rows[i]["suggested_category_id"] = cat["id"] if cat else None
                rows[i]["suggested_category_name"] = cat["name"] if cat else None
                rows[i]["confidence"] = conf
                rows[i]["categorization_source"] = "heuristic"
                rows[i]["needs_review"] = bool(rows[i]["is_duplicate"] or conf < 0.80)

        return {"staged_rows": rows}

    async def human_review_gate_node(state: IngestionState) -> dict[str, Any]:
        """Pause graph via LangGraph interrupt() so the user can review/edit staged rows."""
        staged = state.get("staged_rows", [])
        review_payload = interrupt(
            {
                "batch_id": state.get("batch_id"),
                "total_rows": len(staged),
                "duplicate_rows": sum(1 for r in staged if r.get("is_duplicate")),
                "needs_review_rows": sum(1 for r in staged if r.get("needs_review")),
                "balance_reconciled": state.get("balance_reconciled"),
                "reconciliation_note": state.get("reconciliation_note"),
            }
        )

        # Graph resumed with user decisions from SvelteKit HITL Review Queue
        decisions_by_idx: dict[int, dict[str, Any]] = {}
        skip_duplicates = True
        learn_from_edits = True

        if isinstance(review_payload, dict):
            skip_duplicates = bool(review_payload.get("skip_duplicates", True))
            learn_from_edits = bool(review_payload.get("learn_from_edits", True))
            for dec in review_payload.get("decisions", []):
                if "row_index" in dec:
                    decisions_by_idx[int(dec["row_index"])] = dec

        categories_by_id = {c["id"]: c for c in state.get("categories", [])}
        approved: list[StagedRowDict] = []
        learning: list[dict[str, str]] = []

        for row in staged:
            merged = dict(row)
            dec = decisions_by_idx.get(row["row_index"])
            if dec:
                merged["user_approved"] = bool(dec.get("user_approved", merged.get("user_approved", True)))
                if dec.get("merchant_clean"):
                    merged["merchant_clean"] = str(dec["merchant_clean"])[:160]
                if "category_id" in dec and dec["category_id"] is not None:
                    merged["suggested_category_id"] = str(dec["category_id"])
                    cat = categories_by_id.get(str(dec["category_id"]))
                    merged["suggested_category_name"] = cat["name"] if cat else None
                if dec.get("direction"):
                    merged["direction"] = dec["direction"]
                if dec.get("amount"):
                    merged["amount"] = str(dec["amount"])
                if dec.get("occurred_at"):
                    merged["occurred_at"] = str(dec["occurred_at"])
                if dec.get("description") is not None:
                    merged["description"] = dec["description"]

            if skip_duplicates and merged.get("is_duplicate") and not (dec and dec.get("user_approved")):
                continue

            if merged.get("user_approved", True):
                approved.append(merged)  # type: ignore[arg-type]
                if learn_from_edits and merged.get("suggested_category_id"):
                    cat = categories_by_id.get(str(merged["suggested_category_id"]))
                    learning.append(
                        {
                            "merchant_raw": merged["merchant_raw"],
                            "merchant_clean": merged["merchant_clean"],
                            "category_id": str(merged["suggested_category_id"]),
                            "category_name": cat["name"] if cat else "",
                        }
                    )

        return {
            "approved_rows": approved,
            "learning_examples": learning,
        }

    graph = StateGraph(IngestionState)
    graph.add_node("parse_document", parse_document_node)
    graph.add_node("dedupe_transactions", dedupe_transactions_node)
    graph.add_node("categorize_transactions", categorize_transactions_node)
    graph.add_node("human_review_gate", human_review_gate_node)

    graph.add_edge(START, "parse_document")
    graph.add_edge("parse_document", "dedupe_transactions")
    graph.add_edge("dedupe_transactions", "categorize_transactions")
    graph.add_edge("categorize_transactions", "human_review_gate")
    graph.add_edge("human_review_gate", END)

    saver = checkpointer if checkpointer is not None else MemorySaver()
    return graph.compile(checkpointer=saver)
