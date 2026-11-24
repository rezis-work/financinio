import json
import logging
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal, TypedDict
from urllib.parse import urlparse

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_factory import get_chat_model
from app.models.finance import Account, CategorizationRule, Category, Transaction
from app.models.ingestion import UploadedDocument
from app.models.planning import Budget, FinancialGoal
from app.models.user import User
from app.schemas.planning import DebtInput, DebtPayoffRequest, WhatIfRequest
from app.services.financial_health_service import (
    compute_financial_health_profile,
    evaluate_purchase_decision,
)
from app.services.planning_service import (
    enrich_goal,
    get_budget_overview,
    get_net_worth_overview,
    get_recurring_overview,
    simulate_debt_payoff,
    simulate_what_if,
)
from app.services.vector_service import VectorMemoryBackend, get_vector_service
from app.services.web_search_service import (
    run_openai_live_web_search,
    sanitize_unverified_markdown_links,
)

logger = logging.getLogger(__name__)

RouteName = Literal[
    "decision_advisor",
    "ledger_analyst",
    "document_rag",
    "wealth_strategist",
    "action_proposer",
    "web_researcher",
    "general",
]

WebSearchMode = Literal["auto", "on", "off"]


class AdvisorState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    base_currency: str
    web_search_mode: WebSearchMode
    route: RouteName
    active_agent: str
    recalled_memories: list[str]
    citations: list[dict[str, Any]]
    proposed_action: dict[str, Any] | None
    action_status: str
    executed_result: dict[str, Any] | None


class RouteDecision(BaseModel):
    route: RouteName = Field(
        description=(
            "Choose 'action_proposer' ONLY if the user explicitly asks to create/set/add a budget, financial goal, or categorization rule in the app. "
            "Choose 'web_researcher' if the user asks to search the live web or find current external listings, apartments/rent/real estate, product prices, deals, flights/hotels, bank deposit/mortgage/interest rates, exchange rates, or up-to-date tax/market info. "
            "Choose 'decision_advisor' if the user asks for spending advice, affordability ('can I afford...', 'should I buy...'), "
            "financial checkup/audit/health score, where they are wasting/leaking money, how to save more, or prioritizing debt vs savings vs investing. "
            "Choose 'document_rag' if the user asks to find/search an uploaded receipt, PDF statement, invoice, warranty, or asks you to remember a personal preference/fact. "
            "Choose 'wealth_strategist' if the user specifically asks about net worth history, financial goals progress, Snowball vs Avalanche debt payoff math, or What-If cash flow projections. "
            "Choose 'ledger_analyst' if the user asks factual lookups about spending totals, income, specific transactions, merchants, account balances, budgets, or recurring bills. "
            "Choose 'general' for conceptual personal finance questions that do not need personal account analysis or live web search."
        )
    )
    reasoning: str = Field(description="Brief one-sentence routing explanation")


class ProposedActionSchema(BaseModel):
    action_type: Literal["create_budget", "create_goal", "create_rule"]
    title: str = Field(description="Short action card title, e.g., 'Create Monthly Groceries Budget'")
    summary: str = Field(description="Clear human-readable summary of what will be saved")
    category_name: str | None = None
    amount: float | None = Field(default=None, gt=0)
    rollover: bool = False
    goal_name: str | None = None
    goal_type: Literal[
        "emergency_fund", "savings", "debt_payoff", "investment", "purchase", "retirement"
    ] = "savings"
    target_amount: float | None = Field(default=None, gt=0)
    monthly_contribution: float = 0.0
    match_pattern: str | None = None
    merchant_override: str | None = None


LUNA_SENIOR_CFO_PROMPT = (
    "You are Luna, Financinio's Senior Financial Advisor & Personal CFO (CFP-grade analytical rigor, warm and decisive coaching style).\n\n"
    "CORE OPERATING PRINCIPLES:\n"
    "1. **Lead with the Bottom Line**: Open with a clear 1-2 sentence verdict or executive takeaway (e.g., **Verdict: Affordable**, **Proceed with Caution**, or **Hold Off** for purchase decisions; or the single biggest lever for spending/savings questions).\n"
    "2. **100% Grounded Numbers**: Use ONLY exact verified figures from the Financial Context JSON below. NEVER fabricate balances, transactions, APRs, or percentages. If a metric is zero or missing because the user hasn't imported data yet, say so transparently and tell them what to add.\n"
    "3. **Clean Visual Structure**: Use clean Markdown — short headings (`###`), crisp bullet points, bold key figures, and compact Markdown tables when comparing options, categories, or before/after impacts.\n"
    "4. **Senior Advisory Depth**: Don't just report raw totals — diagnose *why* (emergency runway impact, savings rate vs. 20% benchmark, fixed obligations vs. 50% benchmark, high-APR drag, 5-year opportunity cost, month-over-month leaks) and give concrete trade-offs and smart alternatives.\n"
    "5. **Actionable Next Steps**: Close with 2–3 specific, numbered next steps. When appropriate, offer to create a budget, savings goal, or categorization rule right in chat (e.g., *'Say \"Create a $350 Dining budget\" and I'll set it up for your approval.'*).\n"
    "6. **Professional Guardrail**: Keep guidance objective and educational — you are an AI personal finance advisor & planner, not a licensed CPA, tax attorney, or registered investment fiduciary."
)


def _last_user_text(messages: list[AnyMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return str(m.content)
    return ""


def _extract_ai_text(resp: Any) -> str:
    """Safely extract markdown text from a LangChain AIMessage (handles string or Gemini content blocks)."""
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
        return "\n".join(p for p in parts if p).strip()
    return str(content)


def _extract_grounding_citations(resp: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract clickable web source citations and search queries from Gemini grounding_metadata."""
    resp_meta = getattr(resp, "response_metadata", None) or {}
    gm = resp_meta.get("grounding_metadata") or {}
    if not isinstance(gm, dict):
        return [], []

    queries = [str(q).strip() for q in (gm.get("web_search_queries") or []) if str(q).strip()]
    chunks = gm.get("grounding_chunks") or []
    web_citations: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for ch in chunks:
        if not isinstance(ch, dict):
            continue
        web = ch.get("web")
        if not isinstance(web, dict):
            continue
        uri = str(web.get("uri") or "").strip()
        title = str(web.get("title") or "").strip()
        if not uri or uri in seen_urls:
            continue
        seen_urls.add(uri)
        parsed = urlparse(uri)
        domain = parsed.netloc.replace("www.", "") if parsed.netloc else ""
        # Gemini grounding sometimes returns a vertexaisearch redirect URL while title holds the domain/page name
        display_domain = title if ("." in title and " " not in title) else (domain or "Web")
        label = title or domain or "Web Result"
        web_citations.append(
            {
                "source": "Web Source",
                "label": label[:120],
                "url": uri,
                "domain": display_domain[:64],
            }
        )
        if len(web_citations) >= 8:
            break

    return web_citations, queries


def _heuristic_route(text: str, web_search_mode: WebSearchMode = "auto") -> RouteName:
    low = text.lower()
    if web_search_mode == "on":
        return "web_researcher"
    has_write_verb = any(v in low for v in ("create", "set ", "add ", "make "))
    has_action_noun = any(n in low for n in ("budget", "goal", "rule"))
    if has_write_verb and has_action_noun:
        return "action_proposer"
    if web_search_mode != "off" and any(
        k in low
        for k in (
            "search for",
            "search the web",
            "search online",
            "find me ",
            "find a ",
            "find an ",
            "look up ",
            "browse ",
            "apartment",
            "apartments",
            "flat to rent",
            "rent in ",
            "for rent",
            "for sale",
            "real estate",
            "myhome",
            "ss.ge",
            "korter",
            "airbnb",
            "mortgage rate",
            "deposit rate",
            "interest rate",
            "exchange rate",
            "nbg rate",
            "current price",
            "price of ",
            "cheapest ",
            "best deal",
            "flight to ",
            "flights to ",
            "hotel in ",
            "hotels in ",
            "compare prices",
        )
    ):
        return "web_researcher"
    if any(
        k in low
        for k in (
            "can i afford",
            "should i buy",
            "should i spend",
            "should i get",
            "should i pay",
            "worth buying",
            "afford a",
            "afford to",
            "health score",
            "checkup",
            "financial review",
            "financial audit",
            "wasting money",
            "leaking money",
            "spending leaks",
            "cut back",
            "how can i save",
            "what should i do with",
            "priorities",
            "advice on my spending",
            "decision",
        )
    ):
        return "decision_advisor"
    if any(
        k in low
        for k in ("receipt", "statement pdf", "uploaded document", "invoice", "warranty", "remember that", "remember my")
    ):
        return "document_rag"
    if any(
        k in low
        for k in ("net worth", "snowball", "avalanche", "debt payoff", "what if", "what-if", "retire", "runway", "goal")
    ):
        return "wealth_strategist"
    if any(
        k in low
        for k in (
            "spend",
            "spent",
            "expense",
            "income",
            "balance",
            "account",
            "budget",
            "subscription",
            "recurring",
            "bill",
            "coffee",
            "grocer",
            "dining",
            "month",
            "cash flow",
            "transaction",
        )
    ):
        return "ledger_analyst"
    return "general"


def _extract_purchase_amount(text: str) -> tuple[Decimal | None, bool]:
    """Extract a monetary amount and whether it's a recurring monthly cost from a user question."""
    low = text.lower()
    is_monthly = any(
        k in low for k in ("/mo", "per month", "a month", "monthly", "every month", "each month")
    )
    # Prefer currency-prefixed numbers ($1,500 or 1500 USD) or plain numbers >= 10
    m = re.search(r"(?:[$€£]|usd|eur|gbp|gel)\s*(\d[\d,]*(?:\.\d{1,2})?)", text, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"\b(\d{2,}(?:,\d{3})*(?:\.\d{1,2})?)\b", text)
    if not m:
        return None, is_monthly
    raw_num = m.group(1).replace(",", "")
    try:
        val = Decimal(raw_num)
        if val > 0:
            return val.quantize(Decimal("0.01")), is_monthly
    except Exception:
        pass
    return None, is_monthly


async def _gather_ledger_context(db: AsyncSession, user: User) -> tuple[dict[str, Any], list[dict]]:
    today = date.today()
    start_90d = today - timedelta(days=90)
    month_start = date(today.year, today.month, 1)

    accounts = (
        await db.scalars(
            select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False))
        )
    ).all()
    categories = {
        c.id: c.name
        for c in (await db.scalars(select(Category).where(Category.user_id == user.id))).all()
    }
    txs = (
        await db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user.id,
                Transaction.parent_transaction_id.is_(None),
                Transaction.occurred_at >= start_90d,
            )
            .order_by(Transaction.occurred_at.desc())
        )
    ).all()

    mtd_in = Decimal("0.00")
    mtd_out = Decimal("0.00")
    cat_spend_90d: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    cat_spend_mtd: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    merchant_spend_90d: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))

    for tx in txs:
        if tx.is_transfer:
            continue
        cat_name = categories.get(tx.category_id, "Uncategorized") if tx.category_id else "Uncategorized"
        if tx.direction == "inflow":
            if tx.occurred_at >= month_start:
                mtd_in += tx.base_amount
        else:
            cat_spend_90d[cat_name] += tx.base_amount
            merchant_spend_90d[tx.merchant_clean] += tx.base_amount
            if tx.occurred_at >= month_start:
                mtd_out += tx.base_amount
                cat_spend_mtd[cat_name] += tx.base_amount

    budgets = await get_budget_overview(db, user)
    recurring = await get_recurring_overview(db, user)
    health = await compute_financial_health_profile(db, user)

    context = {
        "as_of": today.isoformat(),
        "base_currency": user.base_currency,
        "financial_health_snapshot": {
            "score": health["health_score"]["overall"],
            "grade": health["health_score"]["grade"],
            "savings_rate_pct": health["cash_flow_ratios"]["savings_rate_pct"],
            "emergency_runway_months": health["cash_flow_ratios"]["emergency_runway_months"],
            "safe_to_spend_remaining": health["cash_flow_ratios"]["safe_to_spend_remaining_this_month"],
            "top_priority": health["health_score"]["top_priority"],
        },
        "accounts": [
            {
                "name": a.name,
                "type": a.type,
                "currency": a.currency,
                "current_balance": f"{a.current_balance:.2f}",
            }
            for a in accounts
        ],
        "month_to_date": {
            "income": f"{mtd_in:.2f}",
            "expenses": f"{mtd_out:.2f}",
            "net": f"{(mtd_in - mtd_out):.2f}",
            "by_category": {
                k: f"{v:.2f}" for k, v in sorted(cat_spend_mtd.items(), key=lambda x: x[1], reverse=True)[:10]
            },
        },
        "last_90_days": {
            "transaction_count": len(txs),
            "top_categories": {
                k: f"{v:.2f}" for k, v in sorted(cat_spend_90d.items(), key=lambda x: x[1], reverse=True)[:10]
            },
            "top_merchants": {
                k: f"{v:.2f}" for k, v in sorted(merchant_spend_90d.items(), key=lambda x: x[1], reverse=True)[:10]
            },
        },
        "budgets": [
            {
                "category": b.category_name,
                "limit": f"{b.effective_limit:.2f}",
                "spent": f"{b.spent:.2f}",
                "remaining": f"{b.remaining:.2f}",
                "status": b.status,
            }
            for b in budgets.budgets
        ],
        "recurring_summary": {
            "monthly_expenses": f"{recurring.monthly_recurring_expenses:.2f}",
            "upcoming_30d": f"{recurring.upcoming_30d_total:.2f}",
            "price_hike_alerts": [
                {
                    "merchant": p.merchant_name,
                    "previous": f"{p.previous_amount:.2f}" if p.previous_amount else None,
                    "current": f"{p.amount:.2f}",
                    "change_pct": f"{p.price_change_pct}%",
                }
                for p in recurring.price_hike_alerts
            ],
        },
    }

    citations = [
        {
            "source": "Neon Ledger",
            "label": f"{len(accounts)} accounts · {len(txs)} transactions (90d)",
        },
        {
            "source": "CFP Health Engine",
            "label": f"Score {health['health_score']['overall']}/100 · {health['cash_flow_ratios']['emergency_runway_months']} mo runway",
        },
    ]
    return context, citations


async def _gather_wealth_context(
    db: AsyncSession, user: User, query_text: str
) -> tuple[dict[str, Any], list[dict]]:
    nw = await get_net_worth_overview(db, user)
    health = await compute_financial_health_profile(db, user)
    goals = (
        await db.scalars(select(FinancialGoal).where(FinancialGoal.user_id == user.id))
    ).all()
    enriched_goals = [enrich_goal(g) for g in goals]

    context: dict[str, Any] = {
        "base_currency": user.base_currency,
        "health_score": health["health_score"],
        "cash_flow_ratios": health["cash_flow_ratios"],
        "net_worth": {
            "assets": f"{nw.current_assets:.2f}",
            "liabilities": f"{nw.current_liabilities:.2f}",
            "net_worth": f"{nw.current_net_worth:.2f}",
            "accounts": [
                {"name": a.name, "type": a.type, "balance": f"{a.balance:.2f}", "class": a.classification}
                for a in nw.accounts
            ],
        },
        "goals": [
            {
                "name": g.name,
                "type": g.goal_type,
                "current": f"{g.current_amount:.2f}",
                "target": f"{g.target_amount:.2f}",
                "progress_pct": g.progress_pct,
                "monthly_contribution": f"{g.monthly_contribution:.2f}",
                "projected_completion": g.projected_completion_date.isoformat()
                if g.projected_completion_date
                else None,
            }
            for g in enriched_goals
        ],
    }
    citations = [
        {"source": "Net Worth Engine", "label": f"Net Worth {user.base_currency} {nw.current_net_worth:.2f}"},
        {"source": "Goals Tracker", "label": f"{len(enriched_goals)} financial goals"},
    ]

    liabilities = [a for a in nw.accounts if a.classification == "liability" and abs(a.balance) > 0]
    if liabilities and any(k in query_text.lower() for k in ("debt", "snowball", "avalanche", "payoff", "loan", "credit")):
        debt_inputs = [
            DebtInput(
                name=acc.name,
                balance=abs(acc.balance),
                apr=Decimal("21.9") if acc.type == "credit" else Decimal("7.5"),
                min_payment=max(Decimal("35.00"), (abs(acc.balance) * Decimal("0.03")).quantize(Decimal("0.01"))),
            )
            for acc in liabilities
        ]
        sim = simulate_debt_payoff(
            DebtPayoffRequest(debts=debt_inputs, extra_monthly_payment=Decimal("200.00"))
        )
        context["debt_simulation_with_200_extra"] = {
            "assumed_aprs_note": "Used 21.9% APR for credit cards and 7.5% for loans unless specified.",
            "recommended": sim.recommended_strategy,
            "avalanche_months": sim.avalanche.months_to_payoff,
            "avalanche_interest": f"{sim.avalanche.total_interest_paid:.2f}",
            "snowball_months": sim.snowball.months_to_payoff,
            "snowball_interest": f"{sim.snowball.total_interest_paid:.2f}",
            "interest_saved_by_avalanche": f"{sim.interest_saved_by_avalanche:.2f}",
            "avalanche_order": sim.avalanche.payoff_order,
        }
        citations.append({"source": "Deterministic Debt Simulator", "label": "Snowball vs. Avalanche (Python Engine)"})

    if any(k in query_text.lower() for k in ("what if", "what-if", "cut", "save more", "raise", "runway")):
        mtd_inc = Decimal(health["cash_flow_ratios"]["avg_monthly_income"])
        mtd_exp = Decimal(health["cash_flow_ratios"]["avg_monthly_expenses"])
        m_amt = re.search(r"\$?\s*(\d+(?:\.\d{1,2})?)", query_text)
        delta = Decimal(m_amt.group(1)) if m_amt else Decimal("250.00")
        is_cut = any(w in query_text.lower() for w in ("cut", "reduce", "less", "save"))
        wi = simulate_what_if(
            WhatIfRequest(
                starting_savings=nw.current_assets,
                monthly_income=mtd_inc if mtd_inc > 0 else Decimal("5000.00"),
                monthly_expenses=mtd_exp if mtd_exp > 0 else Decimal("3800.00"),
                income_delta_monthly=Decimal("0.00") if is_cut else delta,
                expense_delta_monthly=-delta if is_cut else Decimal("0.00"),
                horizon_months=12,
            )
        )
        context["what_if_12m_projection"] = {
            "delta_modeled": f"{'-' if is_cut else '+'}{delta:.2f}/mo",
            "baseline_12m_balance": f"{wi.baseline_end_balance:.2f}",
            "scenario_12m_balance": f"{wi.scenario_end_balance:.2f}",
            "net_12m_impact": f"{wi.net_impact:.2f}",
            "runway_months": wi.scenario_runway_months,
        }
        citations.append({"source": "Deterministic What-If Engine", "label": "12-Month Compounding Projection"})

    return context, citations


async def _execute_action_in_neon(
    db: AsyncSession,
    user: User,
    action: dict[str, Any],
) -> dict[str, Any]:
    action_type = action.get("action_type")
    categories = (
        await db.scalars(select(Category).where(Category.user_id == user.id))
    ).all()
    cat_by_lower = {c.name.lower(): c for c in categories}

    def resolve_category(name: str | None) -> Category | None:
        if not name:
            return None
        low = name.lower().strip()
        if low in cat_by_lower:
            return cat_by_lower[low]
        for cname, cat in cat_by_lower.items():
            if low in cname or cname in low:
                return cat
        return None

    if action_type == "create_budget":
        cat = resolve_category(action.get("category_name")) or next(
            (c for c in categories if c.kind == "expense"), None
        )
        if cat is None:
            raise ValueError("No matching expense category found.")
        amount = Decimal(str(action.get("amount") or 300)).quantize(Decimal("0.01"))
        rollover = bool(action.get("rollover", False))
        existing = await db.scalar(
            select(Budget).where(
                Budget.user_id == user.id,
                Budget.category_id == cat.id,
                Budget.period == "monthly",
            )
        )
        if existing:
            existing.amount = amount
            existing.rollover = rollover
            existing.is_active = True
            budget = existing
        else:
            budget = Budget(
                user_id=user.id,
                category_id=cat.id,
                amount=amount,
                period="monthly",
                rollover=rollover,
            )
            db.add(budget)
        await db.commit()
        await db.refresh(budget)
        return {
            "status": "created",
            "entity": "budget",
            "id": str(budget.id),
            "category": cat.name,
            "amount": f"{budget.amount:.2f}",
            "rollover": budget.rollover,
        }

    if action_type == "create_goal":
        name = str(action.get("goal_name") or action.get("title") or "Savings Goal")[:120]
        target = Decimal(str(action.get("target_amount") or action.get("amount") or 5000)).quantize(
            Decimal("0.01")
        )
        monthly = Decimal(str(action.get("monthly_contribution") or 0)).quantize(Decimal("0.01"))
        goal = FinancialGoal(
            user_id=user.id,
            name=name,
            goal_type=str(action.get("goal_type") or "savings"),
            target_amount=target,
            current_amount=Decimal("0.00"),
            monthly_contribution=monthly,
        )
        db.add(goal)
        await db.commit()
        await db.refresh(goal)
        return {
            "status": "created",
            "entity": "goal",
            "id": str(goal.id),
            "name": goal.name,
            "target_amount": f"{goal.target_amount:.2f}",
        }

    if action_type == "create_rule":
        cat = resolve_category(action.get("category_name"))
        if cat is None:
            raise ValueError("Could not find target category for rule.")
        pattern = str(action.get("match_pattern") or "").strip()
        if not pattern:
            raise ValueError("Rule match_pattern is required.")
        rule = CategorizationRule(
            user_id=user.id,
            match_pattern=pattern,
            match_type="contains",
            category_id=cat.id,
            merchant_override=action.get("merchant_override"),
            priority=50,
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return {
            "status": "created",
            "entity": "rule",
            "id": str(rule.id),
            "match_pattern": rule.match_pattern,
            "category": cat.name,
        }

    raise ValueError(f"Unsupported action_type: {action_type}")


def _heuristic_extract_action(text: str, categories: list[str]) -> dict[str, Any]:
    low = text.lower()
    m_amt = re.search(r"\$?\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)", text)
    amt = float(m_amt.group(1).replace(",", "")) if m_amt else 500.0

    matched_cat = next((c for c in categories if c.lower().split()[0] in low), None)

    if "goal" in low:
        return {
            "action_type": "create_goal",
            "title": "Create Financial Goal",
            "summary": f"Create a new financial goal with target {amt:.2f}.",
            "goal_name": "Emergency Fund" if "emergency" in low else "Personal Savings Goal",
            "goal_type": "emergency_fund" if "emergency" in low else "savings",
            "target_amount": amt,
            "monthly_contribution": round(amt / 12, 2),
        }

    if "rule" in low:
        return {
            "action_type": "create_rule",
            "title": "Create Categorization Rule",
            "summary": f"Auto-categorize matching merchants into {matched_cat or 'Dining & Coffee'}.",
            "match_pattern": text.split()[-1].strip("\"'."),
            "category_name": matched_cat or "Dining & Coffee",
        }

    return {
        "action_type": "create_budget",
        "title": f"Set {matched_cat or 'Monthly'} Budget",
        "summary": f"Create a monthly budget of {amt:.2f} for {matched_cat or 'Dining & Coffee'}.",
        "category_name": matched_cat or "Dining & Coffee",
        "amount": amt,
        "rollover": "rollover" in low,
    }


def build_advisor_graph(
    *,
    db: AsyncSession,
    user: User,
    checkpointer: BaseCheckpointSaver | None = None,
    llm: BaseChatModel | None = None,
    vector_service: VectorMemoryBackend | None = None,
):
    """Build Luna — Financinio's Senior Financial Advisor multi-agent LangGraph system."""
    vec = vector_service if vector_service is not None else get_vector_service()
    model = llm if llm is not None else get_chat_model("fast", temperature=0.2)

    async def recall_memory_node(state: AdvisorState) -> dict[str, Any]:
        query = _last_user_text(state.get("messages", []))
        facts = await vec.recall_user_facts(user.id, query, top_k=4)
        return {
            "recalled_memories": [f.fact for f in facts],
            "citations": [],
            "proposed_action": None,
            "action_status": "none",
            "executed_result": None,
        }

    async def supervisor_router_node(state: AdvisorState) -> dict[str, Any]:
        query = _last_user_text(state.get("messages", []))
        web_mode: WebSearchMode = state.get("web_search_mode") or "auto"
        route: RouteName = _heuristic_route(query, web_mode)

        # If the user explicitly forced live web search ON, go straight to web_researcher
        if web_mode == "on":
            return {"route": "web_researcher", "active_agent": "web_researcher"}

        if model is not None:
            try:
                router_llm = model.with_structured_output(RouteDecision)
                web_hint = (
                    " Live web search is DISABLED by the user — do NOT choose 'web_researcher'."
                    if web_mode == "off"
                    else ""
                )
                decision: RouteDecision = await router_llm.ainvoke(  # type: ignore[assignment]
                    [
                        SystemMessage(
                            content=(
                                "You are the Supervisor Router for Luna, a Senior Personal Finance Advisor & CFO. "
                                f"Pick the best specialist agent.{web_hint}"
                            )
                        ),
                        HumanMessage(content=query),
                    ]
                )
                route = decision.route
            except Exception as exc:
                logger.warning("Supervisor router LLM failed, using heuristic: %s", exc)

        if web_mode == "off" and route == "web_researcher":
            route = _heuristic_route(query, "off")

        return {"route": route, "active_agent": route}

    async def decision_advisor_node(state: AdvisorState) -> dict[str, Any]:
        """Senior CFP Decision Specialist: affordability, spending leaks, trade-offs & checkups."""
        query = _last_user_text(state.get("messages", []))
        profile = await compute_financial_health_profile(db, user)
        memories = state.get("recalled_memories", [])
        citations = [
            {
                "source": "Senior CFP Diagnostic",
                "label": f"Health Score {profile['health_score']['overall']}/100 ({profile['health_score']['grade']})",
            },
            {
                "source": "Cash Flow & Runway",
                "label": f"Savings {profile['cash_flow_ratios']['savings_rate_pct']}% · Runway {profile['cash_flow_ratios']['emergency_runway_months']} mo",
            },
        ]

        # Run deterministic affordability engine whenever a purchase amount is mentioned
        purchase_eval: dict[str, Any] | None = None
        if any(
            k in query.lower()
            for k in ("afford", "buy", "purchase", "spend", "trip", "car", "laptop", "phone", "rent", "lease", "cost")
        ):
            amt, is_monthly = _extract_purchase_amount(query)
            if amt is not None:
                purchase_eval = evaluate_purchase_decision(
                    profile, amount=amt, is_recurring_monthly=is_monthly
                )
                citations.append(
                    {
                        "source": "Affordability Engine",
                        "label": f"Verdict: {purchase_eval['verdict'].replace('_', ' ')}",
                    }
                )

        payload = {
            "financial_health_profile": profile,
            "purchase_affordability_analysis": purchase_eval,
        }

        if model is not None:
            sys_prompt = (
                f"{LUNA_SENIOR_CFO_PROMPT}\n\n"
                f"Active Specialist: **Senior CFP Decision Advisor**.\n"
                f"Remembered User Preferences/Goals: {memories}\n"
                f"Verified Diagnostic & Decision Data (JSON):\n{json.dumps(payload, indent=2)}\n\n"
                "Deliver an executive-grade advisory response:\n"
                "- Open with a clear **Verdict / Executive Takeaway**.\n"
                "- Include a clean Markdown table of the exact key numbers (e.g., Health Score pillars, or Before vs. After purchase impact & 5-year opportunity cost).\n"
                "- Call out concrete **spending leaks, trade-offs, and smarter alternatives**.\n"
                "- End with 2–3 prioritized, measurable next actions."
            )
            resp = await model.ainvoke([SystemMessage(content=sys_prompt), *state["messages"][-8:]])
            answer = str(resp.content)
        else:
            hs = profile["health_score"]
            cf = profile["cash_flow_ratios"]
            lines = [
                f"### Financial Health Checkup — **{hs['overall']}/100 ({hs['grade']})**",
                "",
                f"**Top Priority:** {hs['top_priority']}",
                "",
                "| Metric | Value |",
                "| :--- | ---: |",
                f"| Savings Rate | {cf['savings_rate_pct']}% |",
                f"| Emergency Runway | {cf['emergency_runway_months']} months |",
                f"| Avg Monthly Surplus | {user.base_currency} {cf['avg_monthly_surplus']} |",
                f"| Safe-to-Spend Remaining | {user.base_currency} {cf['safe_to_spend_remaining_this_month']} |",
            ]
            if purchase_eval:
                lines += [
                    "",
                    f"### Purchase Verdict: **{purchase_eval['verdict'].replace('_', ' ')}**",
                    f"- {purchase_eval['reasons'][0]}",
                    f"- 5-Year Opportunity Cost (at 7%): `{user.base_currency} {purchase_eval['five_year_opportunity_cost_at_7pct']}`",
                ]
            answer = "\n".join(lines)

        return {
            "messages": [AIMessage(content=answer)],
            "active_agent": "decision_advisor",
            "citations": citations,
        }

    async def ledger_analyst_node(state: AdvisorState) -> dict[str, Any]:
        query = _last_user_text(state.get("messages", []))
        context, citations = await _gather_ledger_context(db, user)
        memories = state.get("recalled_memories", [])

        if model is not None:
            sys_prompt = (
                f"{LUNA_SENIOR_CFO_PROMPT}\n\n"
                f"Active Specialist: **Senior Ledger & Cash Flow Analyst**.\n"
                f"Remembered User Facts: {memories}\n"
                f"Verified Financial Context (JSON):\n{json.dumps(context, indent=2)}\n\n"
                "Answer with precision AND add one proactive CFO insight (e.g., category concentration, pacing, or a concrete savings opportunity)."
            )
            resp = await model.ainvoke([SystemMessage(content=sys_prompt), *state["messages"][-8:]])
            answer = str(resp.content)
        else:
            mtd = context["month_to_date"]
            answer = (
                f"### Month-to-Date Snapshot ({user.base_currency})\n\n"
                f"- **Income:** `{mtd['income']}`\n"
                f"- **Expenses:** `{mtd['expenses']}`\n"
                f"- **Net Cash Flow:** `{mtd['net']}`\n"
                f"- **Active Accounts:** {len(context['accounts'])}\n\n"
                f"*(Configure an LLM API key in `.env` for richer natural-language analysis on: \"{query}\")*"
            )

        return {
            "messages": [AIMessage(content=answer)],
            "active_agent": "ledger_analyst",
            "citations": citations,
        }

    async def document_rag_node(state: AdvisorState) -> dict[str, Any]:
        query = _last_user_text(state.get("messages", []))
        citations: list[dict[str, Any]] = []
        saved_fact: str | None = None

        if any(k in query.lower() for k in ("remember that", "remember my", "save to memory", "note that i")):
            fact_item = await vec.remember_user_fact(user.id, query, category="user_note")
            saved_fact = fact_item.fact
            citations.append({"source": "Upstash User Memory", "label": f"Saved memory ({fact_item.id})"})

        doc_matches = await vec.search_documents(user.id, query, top_k=4)
        for m in doc_matches:
            citations.append(
                {
                    "source": f"Document RAG ({m.doc_type})",
                    "label": f"{m.filename} (match {int(m.score * 100)}%)",
                }
            )

        neon_docs = (
            await db.scalars(
                select(UploadedDocument)
                .where(UploadedDocument.user_id == user.id)
                .order_by(UploadedDocument.created_at.desc())
                .limit(5)
            )
        ).all()

        rag_context = {
            "saved_fact": saved_fact,
            "vector_matches": [
                {
                    "filename": m.filename,
                    "doc_type": m.doc_type,
                    "score": m.score,
                    "excerpt": m.excerpt,
                }
                for m in doc_matches
            ],
            "recent_uploaded_documents": [
                {"filename": d.filename, "doc_type": d.doc_type, "excerpt": (d.extracted_text or "")[:300]}
                for d in neon_docs
            ],
        }

        if model is not None:
            sys_prompt = (
                f"{LUNA_SENIOR_CFO_PROMPT}\n\n"
                f"Active Specialist: **Document & Memory RAG Agent (Upstash Vector)**.\n"
                f"Retrieved Documents & Memory Context:\n{json.dumps(rag_context, indent=2)}"
            )
            resp = await model.ainvoke([SystemMessage(content=sys_prompt), *state["messages"][-6:]])
            answer = str(resp.content)
        else:
            if saved_fact:
                answer = f"Got it — I've saved that to your personal Upstash Vector memory: *\"{saved_fact}\"*."
            elif doc_matches:
                lines = [f"- **{m.filename}** ({int(m.score * 100)}% match): {m.excerpt[:180]}" for m in doc_matches]
                answer = "Here is what I found in your uploaded documents:\n" + "\n".join(lines)
            else:
                answer = "I searched your uploaded receipts & PDF statements in Upstash Vector and didn't find a matching document yet."

        return {
            "messages": [AIMessage(content=answer)],
            "active_agent": "document_rag",
            "citations": citations,
        }

    async def wealth_strategist_node(state: AdvisorState) -> dict[str, Any]:
        query = _last_user_text(state.get("messages", []))
        context, citations = await _gather_wealth_context(db, user, query)
        memories = state.get("recalled_memories", [])

        if model is not None:
            sys_prompt = (
                f"{LUNA_SENIOR_CFO_PROMPT}\n\n"
                f"Active Specialist: **Senior Wealth & Debt Strategist** (backed by deterministic Python simulators).\n"
                f"Remembered User Facts: {memories}\n"
                f"Verified Wealth & Simulation Data:\n{json.dumps(context, indent=2)}\n\n"
                "Present clear strategy comparisons (e.g., Snowball vs. Avalanche table, timeline, interest saved) and explain the trade-offs."
            )
            resp = await model.ainvoke([SystemMessage(content=sys_prompt), *state["messages"][-8:]])
            answer = str(resp.content)
        else:
            nw = context["net_worth"]
            answer = (
                f"### Wealth Snapshot ({user.base_currency})\n\n"
                f"- **Total Assets:** `{nw['assets']}`\n"
                f"- **Total Liabilities:** `{nw['liabilities']}`\n"
                f"- **Net Worth:** `{nw['net_worth']}`\n"
                f"- **Active Goals:** {len(context['goals'])}"
            )

        return {
            "messages": [AIMessage(content=answer)],
            "active_agent": "wealth_strategist",
            "citations": citations,
        }

    async def action_proposer_node(state: AdvisorState) -> dict[str, Any]:
        query = _last_user_text(state.get("messages", []))
        categories = (
            await db.scalars(select(Category).where(Category.user_id == user.id))
        ).all()
        cat_names = [c.name for c in categories]

        proposal: dict[str, Any]
        if model is not None:
            try:
                extractor = model.with_structured_output(ProposedActionSchema)
                parsed: ProposedActionSchema = await extractor.ainvoke(  # type: ignore[assignment]
                    [
                        SystemMessage(
                            content=(
                                "Extract the financial action the user wants to execute in Financinio. "
                                f"Available categories: {', '.join(cat_names)}. "
                                f"User currency: {user.base_currency}."
                            )
                        ),
                        HumanMessage(content=query),
                    ]
                )
                proposal = parsed.model_dump()
            except Exception as exc:
                logger.warning("Action proposer LLM failed, using heuristic: %s", exc)
                proposal = _heuristic_extract_action(query, cat_names)
        else:
            proposal = _heuristic_extract_action(query, cat_names)

        decision = interrupt(
            {
                "type": "hitl_action_approval",
                "action": proposal,
            }
        )

        approved = bool(isinstance(decision, dict) and decision.get("approved"))
        if not approved:
            return {
                "messages": [
                    AIMessage(
                        content=f"No problem — I canceled **{proposal.get('title', 'that action')}**. Nothing was changed in your account."
                    )
                ],
                "active_agent": "action_proposer",
                "proposed_action": proposal,
                "action_status": "rejected",
                "executed_result": None,
            }

        final_params = {**proposal, **(decision.get("override_params") or {})}
        result = await _execute_action_in_neon(db, user, final_params)

        confirm_text = (
            f"Done! I executed **{final_params.get('title', 'your action')}** and saved it to your ledger.\n\n"
            f"- Details: `{json.dumps(result)}`"
        )
        return {
            "messages": [AIMessage(content=confirm_text)],
            "active_agent": "action_proposer",
            "proposed_action": final_params,
            "action_status": "executed",
            "executed_result": result,
            "citations": [{"source": "HITL Action Executed", "label": f"Saved {result.get('entity')} to Neon"}],
        }

    async def web_researcher_node(state: AdvisorState) -> dict[str, Any]:
        """Live Web Research Agent (OpenAI Responses web_search & Gemini Google Search) + real budget limits."""
        query = _last_user_text(state.get("messages", []))
        profile = await compute_financial_health_profile(db, user)
        cf = profile["cash_flow_ratios"]
        bs = profile["balance_sheet"]

        avg_income = Decimal(str(cf.get("avg_monthly_income") or "0"))
        safe_housing_30 = (avg_income * Decimal("0.30")).quantize(Decimal("0.01"))
        safe_housing_25 = (avg_income * Decimal("0.25")).quantize(Decimal("0.01"))

        # Strict PII guardrail: pass ONLY anonymized numeric affordability benchmarks
        budget_benchmarks = {
            "as_of": date.today().isoformat(),
            "base_currency": user.base_currency,
            "avg_monthly_income": cf["avg_monthly_income"],
            "avg_monthly_expenses": cf["avg_monthly_expenses"],
            "avg_monthly_surplus": cf["avg_monthly_surplus"],
            "safe_housing_rent_cap_25pct": f"{safe_housing_25:.2f}",
            "safe_housing_rent_cap_30pct": f"{safe_housing_30:.2f}",
            "liquid_cash_available": bs["liquid_cash"],
            "emergency_runway_months": cf["emergency_runway_months"],
            "safe_to_spend_this_month": cf["safe_to_spend_remaining_this_month"],
        }

        citations: list[dict[str, Any]] = [
            {
                "source": "CFP Budget Guardrail",
                "label": (
                    f"Safe housing ≤ {user.base_currency} {safe_housing_30:.0f}/mo · "
                    f"Surplus {user.base_currency} {cf['avg_monthly_surplus']}/mo"
                ),
            }
        ]

        if model is not None:
            sys_prompt = (
                f"{LUNA_SENIOR_CFO_PROMPT}\n\n"
                "Active Specialist: **Live Web Research & Budget Match Agent**.\n"
                "PRIVACY RULE: NEVER include the user's personal identity or raw account info in web searches — use only generic public search terms (city, neighborhood, price range, currency, product/service).\n\n"
                f"User's Real Financial Affordability Benchmarks (JSON):\n{json.dumps(budget_benchmarks, indent=2)}\n\n"
                "STRICT URL INTEGRITY RULE (CRITICAL):\n"
                "- You MUST run a live web search before answering.\n"
                "- ONLY link to EXACT verbatim URLs actually returned in the live web search tool results.\n"
                "- NEVER guess, invent, or synthesize a URL slug (for example, NEVER write fake paths like `myhome.ge/en/for-sale/apartment/1-bedroom-70k`).\n"
                "- If search returns category/search pages or market guides rather than individual listing URLs, link ONLY to the exact verified pages returned and tell the user honestly.\n\n"
                "RESEARCH & RESPONSE INSTRUCTIONS:\n"
                "1. Search the live web for current, real-world listings, prices, or rates matching the user's request "
                "(for Georgia/Tbilisi housing, search portals like myhome.ge, ss.ge, korter.ge, livo.ge; for banking/rates search nbg.gov.ge, bog.ge, tbcbank.ge).\n"
                "2. Open with a crisp **Budget Ceiling & Search Verdict** tying their real monthly income/surplus or liquid cash (or any explicit budget they stated) to live market prices.\n"
                "3. Present ONLY verified results found via live search in a clean **Markdown table** with:\n"
                "   - Option / Listing / Neighborhood / Provider\n"
                "   - Verified Price / Rate from search results\n"
                "   - **Budget Fit Verdict** (e.g., `Fits Budget`, `Tight`, or `Over Budget`)\n"
                "   - Exact verified clickable link from search results\n"
                "4. Close with 2–3 concrete next steps (e.g., offer to set up a purchase/moving savings goal right in chat)."
            )

            model_cls = model.__class__.__name__
            answer = ""
            web_cits: list[dict[str, Any]] = []
            search_queries: list[str] = []

            # Path A: OpenAI Responses API live web_search (real verified URLs!)
            if model_cls == "ChatOpenAI":
                conv_msgs: list[dict[str, str]] = []
                for m in state["messages"][-6:]:
                    role = "user" if isinstance(m, HumanMessage) else "assistant"
                    conv_msgs.append({"role": role, "content": str(m.content)})
                try:
                    live_res = await run_openai_live_web_search(
                        system_instructions=sys_prompt,
                        conversation_messages=conv_msgs,
                    )
                    if live_res is not None:
                        answer = live_res.answer_text
                        web_cits = live_res.citations
                        search_queries = live_res.search_queries
                        if search_queries:
                            citations.append(
                                {
                                    "source": "Live Web Search",
                                    "label": " · ".join(search_queries[:3])[:140],
                                }
                            )
                        else:
                            citations.append(
                                {
                                    "source": "Live Web Search",
                                    "label": f"OpenAI Web Search ({live_res.model_name or 'live'})",
                                }
                            )
                        citations.extend(web_cits)
                except Exception as exc:
                    logger.warning("OpenAI live web search failed: %s", exc)

            # Path B: Google Gemini native Google Search grounding
            if not answer and model_cls == "ChatGoogleGenerativeAI" and hasattr(model, "bind_tools"):
                try:
                    search_model = model.bind_tools([{"google_search": {}}])
                    resp = await search_model.ainvoke(
                        [SystemMessage(content=sys_prompt), *state["messages"][-6:]]
                    )
                    raw_answer = _extract_ai_text(resp)
                    web_cits, search_queries = _extract_grounding_citations(resp)
                    verified_urls = {str(c["url"]) for c in web_cits if c.get("url")}
                    answer = sanitize_unverified_markdown_links(raw_answer, verified_urls)
                    if search_queries:
                        citations.append(
                            {
                                "source": "Google Search",
                                "label": " · ".join(search_queries[:3])[:140],
                            }
                        )
                    else:
                        citations.append(
                            {
                                "source": "Google Search",
                                "label": "Live web grounding enabled",
                            }
                        )
                    citations.extend(web_cits)
                except Exception as exc:
                    logger.warning("Gemini Google Search grounding failed: %s", exc)

            # Safe fallback if provider does not support live search or search failed
            if not answer:
                resp = await model.ainvoke(
                    [SystemMessage(content=sys_prompt), *state["messages"][-6:]]
                )
                raw_answer = _extract_ai_text(resp)
                answer = sanitize_unverified_markdown_links(raw_answer, set())
                citations.append(
                    {
                        "source": "Web Search Notice",
                        "label": "Live search temporarily unavailable — unverified deep links stripped",
                    }
                )
        else:
            answer = (
                f"### Live Web Research + Budget Fit ({user.base_currency})\n\n"
                f"Based on your verified Neon ledger, here are your real affordability guardrails for **\"{query}\"**:\n\n"
                "| Budget Benchmark | Value |\n"
                "| :--- | ---: |\n"
                f"| Safe Monthly Housing (30% Rule) | `{user.base_currency} {safe_housing_30:.2f}/mo` |\n"
                f"| Avg Monthly Surplus | `{user.base_currency} {cf['avg_monthly_surplus']}/mo` |\n"
                f"| Liquid Cash Available | `{user.base_currency} {bs['liquid_cash']}` |\n"
                f"| Emergency Runway | `{cf['emergency_runway_months']} months` |\n\n"
                "*(Configure an `OPENAI_API_KEY` or `GOOGLE_API_KEY` on the server to enable live web search.)*"
            )

        return {
            "messages": [AIMessage(content=answer)],
            "active_agent": "web_researcher",
            "citations": citations,
        }

    async def general_coach_node(state: AdvisorState) -> dict[str, Any]:
        memories = state.get("recalled_memories", [])
        health = await compute_financial_health_profile(db, user)
        if model is not None:
            sys_prompt = (
                f"{LUNA_SENIOR_CFO_PROMPT}\n\n"
                f"Remembered User Facts: {memories}\n"
                f"User Quick Context (for personalizing advice when relevant):\n"
                f"{json.dumps({'health_score': health['health_score'], 'cash_flow_ratios': health['cash_flow_ratios']}, indent=2)}\n\n"
                "Give practical, senior-level financial guidance tailored to their situation."
            )
            resp = await model.ainvoke([SystemMessage(content=sys_prompt), *state["messages"][-8:]])
            answer = _extract_ai_text(resp)
        else:
            answer = (
                "Hi! I'm **Luna**, your Senior Financial Advisor. Ask me whether you can afford a purchase, "
                "to search live apartments or prices in your budget, run a Financial Health Checkup, "
                "find spending leaks, or create a budget or goal!"
            )
        return {
            "messages": [AIMessage(content=answer)],
            "active_agent": "general",
            "citations": [],
        }

    def route_selector(state: AdvisorState) -> str:
        return state.get("route", "general")

    graph = StateGraph(AdvisorState)
    graph.add_node("recall_memory", recall_memory_node)
    graph.add_node("supervisor_router", supervisor_router_node)
    graph.add_node("decision_advisor", decision_advisor_node)
    graph.add_node("ledger_analyst", ledger_analyst_node)
    graph.add_node("document_rag", document_rag_node)
    graph.add_node("wealth_strategist", wealth_strategist_node)
    graph.add_node("action_proposer", action_proposer_node)
    graph.add_node("web_researcher", web_researcher_node)
    graph.add_node("general", general_coach_node)

    graph.add_edge(START, "recall_memory")
    graph.add_edge("recall_memory", "supervisor_router")
    graph.add_conditional_edges(
        "supervisor_router",
        route_selector,
        {
            "decision_advisor": "decision_advisor",
            "ledger_analyst": "ledger_analyst",
            "document_rag": "document_rag",
            "wealth_strategist": "wealth_strategist",
            "action_proposer": "action_proposer",
            "web_researcher": "web_researcher",
            "general": "general",
        },
    )
    graph.add_edge("decision_advisor", END)
    graph.add_edge("ledger_analyst", END)
    graph.add_edge("document_rag", END)
    graph.add_edge("wealth_strategist", END)
    graph.add_edge("action_proposer", END)
    graph.add_edge("web_researcher", END)
    graph.add_edge("general", END)

    saver = checkpointer if checkpointer is not None else MemorySaver()
    return graph.compile(checkpointer=saver)
