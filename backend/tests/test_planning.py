from datetime import date, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_budgets_rollover_and_template(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    acc = (
        await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={"name": "Checking", "type": "checking", "currency": "USD", "initial_balance": "3000.00"},
        )
    ).json()

    cats = (await client.get("/api/v1/categories", headers=auth_headers)).json()
    dining_cat = next(c for c in cats if c["name"] == "Dining & Coffee")

    # Spend $120 last month and $350 this month against a $300/mo rollover budget
    today = date.today()
    prev_month_day = (today.replace(day=1) - timedelta(days=5)).isoformat()
    curr_month_day = today.isoformat()

    await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": acc["id"],
            "category_id": dining_cat["id"],
            "amount": "120.00",
            "direction": "outflow",
            "occurred_at": prev_month_day,
            "merchant": "Cafe Prev",
        },
    )
    await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": acc["id"],
            "category_id": dining_cat["id"],
            "amount": "350.00",
            "direction": "outflow",
            "occurred_at": curr_month_day,
            "merchant": "Bistro Curr",
        },
    )

    resp = await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={
            "category_id": dining_cat["id"],
            "amount": "300.00",
            "period": "monthly",
            "rollover": True,
            "alert_threshold_pct": 80,
        },
    )
    assert resp.status_code == 201, resp.text
    overview = resp.json()
    assert len(overview["budgets"]) == 1
    b = overview["budgets"][0]
    # Unspent from previous month = 300 - 120 = 180 -> effective limit = 480
    assert b["rollover_carry"] == "180.00"
    assert b["effective_limit"] == "480.00"
    assert b["spent"] == "350.00"
    assert b["remaining"] == "130.00"

    # Apply 50/30/20 template
    tpl = await client.post(
        "/api/v1/budgets/apply-50-30-20",
        headers=auth_headers,
        json={"monthly_income": "6000.00"},
    )
    assert tpl.status_code == 200
    assert len(tpl.json()["budgets"]) >= 8


@pytest.mark.asyncio
async def test_recurring_detector_catches_price_hike(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    acc = (
        await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={"name": "Card", "type": "credit", "currency": "USD", "initial_balance": "0.00"},
        )
    ).json()

    today = date.today()
    # 3 monthly Netflix charges with a hike from $15.99 -> $19.99 on the latest bill
    dates_and_amounts = [
        (today - timedelta(days=62), "15.99"),
        (today - timedelta(days=32), "15.99"),
        (today - timedelta(days=2), "19.99"),
    ]
    for occ, amt in dates_and_amounts:
        r = await client.post(
            "/api/v1/transactions",
            headers=auth_headers,
            json={
                "account_id": acc["id"],
                "amount": amt,
                "direction": "outflow",
                "occurred_at": occ.isoformat(),
                "merchant": "Netflix",
            },
        )
        assert r.status_code == 201

    det = await client.post("/api/v1/recurring/detect", headers=auth_headers)
    assert det.status_code == 200, det.text
    body = det.json()
    assert body["detected_new"] == 1
    assert body["price_hikes_found"] == 1
    assert len(body["overview"]["price_hike_alerts"]) == 1
    alert = body["overview"]["price_hike_alerts"][0]
    assert alert["merchant_name"] == "Netflix"
    assert alert["cadence"] == "monthly"
    assert alert["previous_amount"] == "15.99"
    assert alert["amount"] == "19.99"


@pytest.mark.asyncio
async def test_net_worth_goals_and_simulators(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # Accounts for Net Worth
    await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Savings", "type": "savings", "currency": "USD", "initial_balance": "12000.00"},
    )
    await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Auto Loan", "type": "loan", "currency": "USD", "initial_balance": "-4500.00"},
    )

    snap = await client.post("/api/v1/wealth/net-worth/snapshot", headers=auth_headers)
    assert snap.status_code == 201
    assert snap.json()["net_worth"] == "7500.00"

    nw = (await client.get("/api/v1/wealth/net-worth", headers=auth_headers)).json()
    assert nw["current_assets"] == "12000.00"
    assert nw["current_liabilities"] == "4500.00"
    assert nw["current_net_worth"] == "7500.00"
    assert len(nw["snapshots"]) == 1

    # Goal creation + contribution
    goal = (
        await client.post(
            "/api/v1/wealth/goals",
            headers=auth_headers,
            json={
                "name": "Emergency Fund",
                "goal_type": "emergency_fund",
                "target_amount": "10000.00",
                "current_amount": "6000.00",
                "monthly_contribution": "500.00",
                "target_date": (date.today() + timedelta(days=365)).isoformat(),
            },
        )
    ).json()
    assert goal["progress_pct"] == 60.0
    assert goal["projected_completion_date"] is not None

    contrib = (
        await client.post(
            f"/api/v1/wealth/goals/{goal['id']}/contribute",
            headers=auth_headers,
            json={"amount": "4000.00"},
        )
    ).json()
    assert contrib["is_completed"] is True
    assert contrib["progress_pct"] == 100.0

    # Debt Payoff Simulator: Avalanche saves interest over Snowball
    debt_sim = await client.post(
        "/api/v1/wealth/simulate/debt-payoff",
        headers=auth_headers,
        json={
            "debts": [
                {"name": "Small Low APR", "balance": "2000.00", "apr": "6.0", "min_payment": "70.00"},
                {"name": "Large High APR", "balance": "8000.00", "apr": "24.0", "min_payment": "200.00"},
            ],
            "extra_monthly_payment": "300.00",
        },
    )
    assert debt_sim.status_code == 200
    ds = debt_sim.json()
    assert float(ds["interest_saved_by_avalanche"]) > 0
    assert ds["recommended_strategy"] == "avalanche"
    assert ds["avalanche"]["payoff_order"][0] == "Large High APR"
    assert ds["snowball"]["payoff_order"][0] == "Small Low APR"

    # What-If Cash Flow Simulator
    what_if = await client.post(
        "/api/v1/wealth/simulate/what-if",
        headers=auth_headers,
        json={
            "starting_savings": "10000.00",
            "monthly_income": "5000.00",
            "monthly_expenses": "4000.00",
            "income_delta_monthly": "500.00",
            "expense_delta_monthly": "-300.00",
            "annual_return_pct": "5.0",
            "horizon_months": 12,
        },
    )
    assert what_if.status_code == 200
    wi = what_if.json()
    assert wi["baseline_monthly_net"] == "1000.00"
    assert wi["scenario_monthly_net"] == "1800.00"
    assert float(wi["net_impact"]) > 9600.0
    assert len(wi["points"]) == 13
