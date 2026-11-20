from datetime import date

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_accounts_transactions_transfers_and_dashboard(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # Create Checking + Savings + Credit Card
    chk = (
        await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={
                "name": "Main Checking",
                "type": "checking",
                "currency": "USD",
                "initial_balance": "2000.00",
                "institution": "Chase",
            },
        )
    ).json()
    sav = (
        await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={
                "name": "High Yield Savings",
                "type": "savings",
                "currency": "USD",
                "initial_balance": "5000.00",
            },
        )
    ).json()
    cc = (
        await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={
                "name": "Sapphire Card",
                "type": "credit",
                "currency": "USD",
                "initial_balance": "-300.00",
            },
        )
    ).json()

    cats = (await client.get("/api/v1/categories", headers=auth_headers)).json()
    salary_cat = next(c for c in cats if c["name"] == "Salary & Payroll")
    groceries_cat = next(c for c in cats if c["name"] == "Groceries")

    today_str = date.today().isoformat()

    # Inflow: Salary +4000
    r1 = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": chk["id"],
            "category_id": salary_cat["id"],
            "amount": "4000.00",
            "direction": "inflow",
            "occurred_at": today_str,
            "merchant": "ACME CORP PAYROLL",
        },
    )
    assert r1.status_code == 201

    # Outflow: Groceries -150 on credit card
    r2 = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": cc["id"],
            "category_id": groceries_cat["id"],
            "amount": "150.00",
            "direction": "outflow",
            "occurred_at": today_str,
            "merchant": "WHOLE FOODS MARKET #102",
        },
    )
    assert r2.status_code == 201

    # Internal transfer: Checking -> Savings 500 (should NOT inflate income or expenses)
    r3 = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": chk["id"],
            "transfer_account_id": sav["id"],
            "amount": "500.00",
            "direction": "outflow",
            "occurred_at": today_str,
            "merchant": "Monthly Savings Transfer",
            "is_transfer": True,
        },
    )
    assert r3.status_code == 201
    assert r3.json()["transfer_peer_id"] is not None

    # Verify recalculated balances
    accounts = {
        a["id"]: a
        for a in (await client.get("/api/v1/accounts", headers=auth_headers)).json()
    }
    assert accounts[chk["id"]]["current_balance"] == "5500.00"  # 2000 + 4000 - 500
    assert accounts[sav["id"]]["current_balance"] == "5500.00"  # 5000 + 500
    assert accounts[cc["id"]]["current_balance"] == "-450.00"  # -300 - 150

    # Verify Dashboard Summary
    dash = (await client.get("/api/v1/dashboard/summary", headers=auth_headers)).json()
    assert dash["total_assets"] == "11000.00"
    assert dash["total_liabilities"] == "450.00"
    assert dash["net_worth"] == "10550.00"
    assert dash["period_income"] == "4000.00"
    assert dash["period_expenses"] == "150.00"
    assert dash["period_net"] == "3850.00"
