import json
import logging
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal, TypedDict

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
from app.services.planning_service import (
    enrich_goal,
    get_budget_overview,
    get_net_worth_overview,
    get_recurring_overview,
    simulate_debt_payoff,
    simulate_what_if,
)
from app.services.vector_service import VectorMemoryBackend, get_vector_service

logger = logging.getLogger(__name__)

RouteName = Literal[
    "ledger_analyst",
    "document_rag",
    "wealth_strategist",
    "action_proposer",
    "general",
]


class AdvisorState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    base_currency: str
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
            "Choose 'action_proposer' if the user asks to create/set/add a budget, financial goal, or categorization rule. "
            "Choose 'document_rag' if the user asks to find/search an uploaded receipt, PDF statement, invoice, or asks you to remember a personal preference/fact. "
            "Choose 'wealth_strategist' if the user asks about net worth, financial goals progress, debt payoff (snowball/avalanche), or what-if cash flow scenarios. "
            "Choose 'ledger_analyst' if the user asks about spending, income, transactions, merchants, account balances, budgets, or recurring bills/subscriptions. "
            "Choose 'general' for general personal finance advice not requiring ledger lookup."
        )
    )
    reasoning: str = Field(description="Brief one-sentence routing explanation")


class ProposedActionSchema(BaseModel):
    action_type: Literal["create_budget", "create_goal", "create_rule"]
    title: str = Field(description="Short action card title, e.g., 'Create Monthly Groceries Budget'")
    summary: str = Field(description="Clear human-readable summary of what will be saved")
    # create_budget params
    category_name: str | None = None
    amount: float | None = Field(default=None, gt=0)
    rollover: bool = False
    # create_goal params
    goal_name: str | None = None
    goal_type: Literal[
        "emergency_fund", "savings", "debt_payoff", "investment", "purchase", "retirement"
    ] = "savings"
    target_amount: float | None = Field(default=None, gt=0)
    monthly_contribution: float = 0.0
    # create_rule params
    match_pattern: str | None = None
    merchant_override: str | None = None


LUNA_SYSTEM_GUARDRAILS = (
    "You are Luna, Financinio's AI personal finance advisor. "
    "Rules:\n"
    "1. Use ONLY the exact numbers provided in the Verified Financial Context — NEVER invent or guess dollar amounts.\n"
    "2. Format numbers cleanly with currency symbols and keep responses structured, actionable, and concise (markdown bullets/tables).\n"
    "3. You provide financial organization and educational planning insights, NOT licensed investment, legal, or tax advice.\n"
    "4. If the user's ledger has no data yet for a question, say so clearly and suggest importing a statement or adding an account."
)


def _last_user_text(messages: list[AnyMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return str(m.content)
    return ""


def _heuristic_route(text: str) -> RouteName:
    low = text.lower()
    has_write_verb = any(v in low for v in ("create", "set ", "add ", "make "))
    has_action_noun = any(n in low for n in ("budget", "goal", "rule"))
    if has_write_verb and has_action_noun:
        return "action_proposer"
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

    context = {
        "as_of": today.isoformat(),
        "base_currency": user.base_currency,
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
            "source": "Budgets & Recurring",
            "label": f"{len(budgets.budgets)} active budgets · {len(recurring.items)} recurring items",
        },
    ]
    return context, citations


async def _gather_wealth_context(
    db: AsyncSession, user: User, query_text: str
) -> tuple[dict[str, Any], list[dict]]:
    nw = await get_net_worth_overview(db, user)
    goals = (
        await db.scalars(select(FinancialGoal).where(FinancialGoal.user_id == user.id))
    ).all()
    enriched_goals = [enrich_goal(g) for g in goals]

    context: dict[str, Any] = {
        "base_currency": user.base_currency,
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

    # Deterministic Debt Payoff simulation if user has liability accounts & asks about debt
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

    # Deterministic What-If sample if asked
    if any(k in query_text.lower() for k in ("what if", "what-if", "cut", "save more", "raise", "runway")):
        ledger_ctx, _ = await _gather_ledger_context(db, user)
        mtd_inc = Decimal(ledger_ctx["month_to_date"]["income"])
        mtd_exp = Decimal(ledger_ctx["month_to_date"]["expenses"])
        # Extract any dollar delta mentioned in user prompt (e.g., "$200")
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
    """Build Luna — Financinio's multi-agent LangGraph financial advisor."""
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
        route: RouteName = _heuristic_route(query)
        if model is not None:
            try:
                router_llm = model.with_structured_output(RouteDecision)
                decision: RouteDecision = await router_llm.ainvoke(  # type: ignore[assignment]
                    [
                        SystemMessage(
                            content="You are the Supervisor Router for Luna, a personal finance AI advisor. Pick the best specialist agent."
                        ),
                        HumanMessage(content=query),
                    ]
                )
                route = decision.route
            except Exception as exc:
                logger.warning("Supervisor router LLM failed, using heuristic: %s", exc)
        return {"route": route, "active_agent": route}

    async def ledger_analyst_node(state: AdvisorState) -> dict[str, Any]:
        query = _last_user_text(state.get("messages", []))
        context, citations = await _gather_ledger_context(db, user)
        memories = state.get("recalled_memories", [])

        if model is not None:
            sys_prompt = (
                f"{LUNA_SYSTEM_GUARDRAILS}\n\n"
                f"Active Specialist: Ledger Analyst.\n"
                f"Remembered User Facts: {memories}\n"
                f"Verified Financial Context (JSON):\n{json.dumps(context, indent=2)}"
            )
            resp = await model.ainvoke([SystemMessage(content=sys_prompt), *state["messages"][-8:]])
            answer = str(resp.content)
        else:
            mtd = context["month_to_date"]
            answer = (
                f"**Month-to-Date Snapshot ({user.base_currency})**:\n"
                f"- Income: `{mtd['income']}`\n"
                f"- Expenses: `{mtd['expenses']}`\n"
                f"- Net Cash Flow: `{mtd['net']}`\n"
                f"- Active Accounts: {len(context['accounts'])}\n\n"
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

        # Detect explicit memory save requests ("remember that I'm saving for...")
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

        # Fallback metadata lookup from Neon uploaded_documents if vector has 0 results
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
                f"{LUNA_SYSTEM_GUARDRAILS}\n\n"
                f"Active Specialist: Document & Memory RAG Agent (Upstash Vector).\n"
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
                f"{LUNA_SYSTEM_GUARDRAILS}\n\n"
                f"Active Specialist: Wealth & Goals Strategist (backed by deterministic Python simulators).\n"
                f"Remembered User Facts: {memories}\n"
                f"Verified Wealth & Simulation Data:\n{json.dumps(context, indent=2)}"
            )
            resp = await model.ainvoke([SystemMessage(content=sys_prompt), *state["messages"][-8:]])
            answer = str(resp.content)
        else:
            nw = context["net_worth"]
            answer = (
                f"**Wealth Snapshot ({user.base_currency})**:\n"
                f"- Total Assets: `{nw['assets']}`\n"
                f"- Total Liabilities: `{nw['liabilities']}`\n"
                f"- **Net Worth**: `{nw['net_worth']}`\n"
                f"- Active Goals: {len(context['goals'])}"
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

        # Pause graph via LangGraph interrupt() so user approves/rejects in SvelteKit!
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

        # Apply any optional parameter overrides from user
        final_params = {**proposal, **(decision.get("override_params") or {})}
        result = await _execute_action_in_neon(db, user, final_params)

        confirm_text = (
            f"Done! I executed **{final_params.get('title', 'your action')}** and saved it to your Neon ledger.\n\n"
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

    async def general_coach_node(state: AdvisorState) -> dict[str, Any]:
        memories = state.get("recalled_memories", [])
        if model is not None:
            sys_prompt = (
                f"{LUNA_SYSTEM_GUARDRAILS}\n\n"
                f"Remembered User Facts: {memories}\n"
                "Answer warmly, clearly, and practically."
            )
            resp = await model.ainvoke([SystemMessage(content=sys_prompt), *state["messages"][-8:]])
            answer = str(resp.content)
        else:
            answer = (
                "Hi! I'm **Luna**, your Financinio AI advisor. Ask me about your spending, "
                "budgets, subscriptions, net worth, uploaded receipts, or ask me to create a budget or goal for you!"
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
    graph.add_node("ledger_analyst", ledger_analyst_node)
    graph.add_node("document_rag", document_rag_node)
    graph.add_node("wealth_strategist", wealth_strategist_node)
    graph.add_node("action_proposer", action_proposer_node)
    graph.add_node("general", general_coach_node)

    graph.add_edge(START, "recall_memory")
    graph.add_edge("recall_memory", "supervisor_router")
    graph.add_conditional_edges(
        "supervisor_router",
        route_selector,
        {
            "ledger_analyst": "ledger_analyst",
            "document_rag": "document_rag",
            "wealth_strategist": "wealth_strategist",
            "action_proposer": "action_proposer",
            "general": "general",
        },
    )
    graph.add_edge("ledger_analyst", END)
    graph.add_edge("document_rag", END)
    graph.add_edge("wealth_strategist", END)
    graph.add_edge("action_proposer", END)
    graph.add_edge("general", END)

    saver = checkpointer if checkpointer is not None else MemorySaver()
    return graph.compile(checkpointer=saver)
