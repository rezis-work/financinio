import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient


def _parse_sse_events(body_text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body_text.strip().split("\n\n"):
        if not block.strip():
            continue
        ev_type = "message"
        data_str = "{}"
        for line in block.splitlines():
            if line.startswith("event:"):
                ev_type = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_str = line[len("data:") :].strip()
        events.append((ev_type, json.loads(data_str)))
    return events


@pytest.mark.asyncio
async def test_luna_sse_chat_and_hitl_budget_action(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # Run tests deterministically offline without hitting live OpenAI
    with patch("app.ai.graphs.advisor_graph.get_chat_model", return_value=None):
        # 1. Create a thread
        th = (
            await client.post("/api/v1/advisor/threads", headers=auth_headers, json={})
        ).json()
        thread_id = th["id"]

        # 2. Ask Luna a ledger question -> streams SSE events
        resp = await client.post(
            f"/api/v1/advisor/threads/{thread_id}/stream",
            headers=auth_headers,
            json={"message": "How much did I spend this month?"},
        )
        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        event_names = [e[0] for e in events]
        assert "status" in event_names
        assert "done" in event_names
        done_msg = next(p["message"] for name, p in events if name == "done")
        assert done_msg["active_agent"] == "ledger_analyst"
        assert len(done_msg["citations"]) >= 1

        # 3. Ask Luna to perform a write action -> triggers LangGraph HITL interrupt()
        act_resp = await client.post(
            f"/api/v1/advisor/threads/{thread_id}/stream",
            headers=auth_headers,
            json={"message": "Create a monthly Groceries budget of $450"},
        )
        assert act_resp.status_code == 200
        act_events = _parse_sse_events(act_resp.text)
        action_ev = next(p["message"] for name, p in act_events if name == "action_required")
        assert action_ev["action_status"] == "pending"
        assert action_ev["pending_action"]["action_type"] == "create_budget"
        assert action_ev["pending_action"]["amount"] == 450.0

        # 4. Approve the HITL Action Card -> resumes LangGraph and writes to DB
        approve = await client.post(
            f"/api/v1/advisor/threads/{thread_id}/actions/{action_ev['id']}",
            headers=auth_headers,
            json={"approved": True},
        )
        assert approve.status_code == 200, approve.text
        res_body = approve.json()
        assert res_body["message"]["action_status"] == "executed"
        assert res_body["executed_result"]["entity"] == "budget"
        assert res_body["executed_result"]["amount"] == "450.00"

        # Verify budget actually exists in /budgets
        budgets = (await client.get("/api/v1/budgets", headers=auth_headers)).json()
        assert any(
            b["category_name"] == "Groceries" and b["amount"] == "450.00"
            for b in budgets["budgets"]
        )


@pytest.mark.asyncio
async def test_user_memories_and_proactive_insights(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    with patch("app.services.insights_service.get_chat_model", return_value=None):
        # 1. User Memory CRUD
        m = await client.post(
            "/api/v1/advisor/memories",
            headers=auth_headers,
            json={"fact": "Saving for a house down payment in late 2027", "category": "goal"},
        )
        assert m.status_code == 201
        mem_id = m.json()["id"]

        mems = (await client.get("/api/v1/advisor/memories", headers=auth_headers)).json()
        assert len(mems) == 1
        assert "house down payment" in mems[0]["fact"]

        del_r = await client.delete(f"/api/v1/advisor/memories/{mem_id}", headers=auth_headers)
        assert del_r.status_code == 204

        # 2. Seed transactions with an unusual large outflow anomaly + duplicate charge
        acc = (
            await client.post(
                "/api/v1/accounts",
                headers=auth_headers,
                json={"name": "Checking", "type": "checking", "currency": "USD", "initial_balance": "4000.00"},
            )
        ).json()
        today = date.today()
        for i, (m_name, amt, days_ago) in enumerate(
            [
                ("Coffee Shop", "10.00", 20),
                ("Lunch Spot", "15.00", 18),
                ("Transit", "12.00", 15),
                ("Bakery", "14.00", 12),
                ("Luxury Electronics", "850.00", 3),
                ("Duplicate Cafe", "24.50", 2),
                ("Duplicate Cafe", "24.50", 1),
            ]
        ):
            r = await client.post(
                "/api/v1/transactions",
                headers=auth_headers,
                json={
                    "account_id": acc["id"],
                    "amount": amt,
                    "direction": "outflow",
                    "occurred_at": (today - timedelta(days=days_ago)).isoformat(),
                    "merchant": m_name,
                    "notes": f"tx-{i}",
                },
            )
            assert r.status_code == 201

        # 3. Generate Proactive Insights
        gen = await client.post("/api/v1/advisor/insights/generate", headers=auth_headers)
        assert gen.status_code == 201, gen.text
        insights = gen.json()
        types = {i["insight_type"] for i in insights}
        assert "weekly_digest" in types
        assert "anomaly" in types


@pytest.mark.asyncio
async def test_senior_cfp_health_score_and_decision_advisor(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    with patch("app.ai.graphs.advisor_graph.get_chat_model", return_value=None):
        # Seed healthy checking account + monthly income & expenses
        acc = (
            await client.post(
                "/api/v1/accounts",
                headers=auth_headers,
                json={
                    "name": "Main Checking",
                    "type": "checking",
                    "currency": "USD",
                    "initial_balance": "12000.00",
                },
            )
        ).json()
        today = date.today()
        await client.post(
            "/api/v1/transactions",
            headers=auth_headers,
            json={
                "account_id": acc["id"],
                "amount": "5500.00",
                "direction": "inflow",
                "occurred_at": (today - timedelta(days=5)).isoformat(),
                "merchant": "Acme Payroll",
            },
        )
        await client.post(
            "/api/v1/transactions",
            headers=auth_headers,
            json={
                "account_id": acc["id"],
                "amount": "2200.00",
                "direction": "outflow",
                "occurred_at": (today - timedelta(days=3)).isoformat(),
                "merchant": "Apartment Rent",
            },
        )

        # 1. Verify Financial Health Score endpoint
        hs_resp = await client.get("/api/v1/advisor/health-score", headers=auth_headers)
        assert hs_resp.status_code == 200, hs_resp.text
        profile = hs_resp.json()
        assert 0 <= profile["health_score"]["overall"] <= 100
        assert set(profile["health_score"]["pillars"].keys()) == {
            "cash_flow_and_savings",
            "emergency_runway",
            "debt_health",
            "budget_and_goals",
        }
        assert profile["health_score"]["top_priority"]
        assert profile["cash_flow_ratios"]["savings_rate_pct"] > 0

        # 2. Stream a Senior CFP purchase affordability decision
        th = (
            await client.post("/api/v1/advisor/threads", headers=auth_headers, json={})
        ).json()
        resp = await client.post(
            f"/api/v1/advisor/threads/{th['id']}/stream",
            headers=auth_headers,
            json={"message": "Can I afford a $1,200 laptop right now?"},
        )
        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        done_msg = next(p["message"] for name, p in events if name == "done")
        assert done_msg["active_agent"] == "decision_advisor"
        citation_sources = {c["source"] for c in done_msg["citations"]}
        assert "Senior CFP Diagnostic" in citation_sources
        assert "Affordability Engine" in citation_sources
        assert "AFFORDABLE" in done_msg["content"] or "Verdict" in done_msg["content"]


def test_web_researcher_routing_and_grounding_extraction() -> None:
    from langchain_core.messages import AIMessage

    from app.ai.graphs.advisor_graph import (
        _extract_ai_text,
        _extract_grounding_citations,
        _heuristic_route,
    )

    assert _heuristic_route("Find me a 2-bedroom apartment to rent in Vake Tbilisi", "auto") == "web_researcher"
    assert _heuristic_route("What is my balance?", "on") == "web_researcher"
    assert _heuristic_route("Find me a 2-bedroom apartment to rent in Vake Tbilisi", "off") != "web_researcher"

    fake_resp = AIMessage(
        content=[{"type": "text", "text": "Found 2 great apartments within your budget."}],
        response_metadata={
            "grounding_metadata": {
                "web_search_queries": ["2 bedroom apartment rent Vake Tbilisi myhome.ge"],
                "grounding_chunks": [
                    {"web": {"uri": "https://www.myhome.ge/en/pr/12345", "title": "myhome.ge"}},
                    {"web": {"uri": "https://ss.ge/en/real-estate/999", "title": "2-Room Flat Vake — ss.ge"}},
                    {"web": {"uri": "https://www.myhome.ge/en/pr/12345", "title": "duplicate"}},
                ],
            }
        },
    )
    assert _extract_ai_text(fake_resp) == "Found 2 great apartments within your budget."
    cits, queries = _extract_grounding_citations(fake_resp)
    assert queries == ["2 bedroom apartment rent Vake Tbilisi myhome.ge"]
    assert len(cits) == 2
    assert cits[0]["url"] == "https://www.myhome.ge/en/pr/12345"
    assert cits[0]["domain"] == "myhome.ge"
    assert cits[1]["source"] == "Web Source"


@pytest.mark.asyncio
async def test_web_researcher_stream_endpoint(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    with patch("app.ai.graphs.advisor_graph.get_chat_model", return_value=None):
        th = (
            await client.post("/api/v1/advisor/threads", headers=auth_headers, json={})
        ).json()
        resp = await client.post(
            f"/api/v1/advisor/threads/{th['id']}/stream",
            headers=auth_headers,
            json={
                "message": "Search for a 2-bedroom apartment to rent in Saburtalo Tbilisi",
                "web_search_mode": "auto",
            },
        )
        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        done_msg = next(p["message"] for name, p in events if name == "done")
        assert done_msg["active_agent"] == "web_researcher"
        assert any(c["source"] == "CFP Budget Guardrail" for c in done_msg["citations"])
        assert "30% Rule" in done_msg["content"]
