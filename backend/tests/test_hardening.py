from datetime import date

import pytest
from httpx import AsyncClient

from app.ai.evals.run_evals import run_all_evals
from app.core.rate_limit import SlidingWindowRateLimiter


@pytest.mark.asyncio
async def test_data_export_csv_json_audit_logs_and_security_headers(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    acc = (
        await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={"name": "Checking", "type": "checking", "currency": "USD", "initial_balance": "1000.00"},
        )
    ).json()

    await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": acc["id"],
            "amount": "42.50",
            "direction": "outflow",
            "occurred_at": date.today().isoformat(),
            "merchant": "Corner Bakery",
        },
    )

    # 1. CSV Export + security headers check
    csv_resp = await client.get("/api/v1/data/export/csv", headers=auth_headers)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert csv_resp.headers.get("x-content-type-options") == "nosniff"
    assert csv_resp.headers.get("x-frame-options") == "DENY"
    assert csv_resp.headers.get("x-request-id")
    assert "Corner Bakery" in csv_resp.text
    assert "42.50" in csv_resp.text

    # 2. Full JSON Backup
    json_resp = await client.get("/api/v1/data/export/json", headers=auth_headers)
    assert json_resp.status_code == 200
    backup = json_resp.json()
    assert backup["version"] == "1.0"
    assert len(backup["accounts"]) == 1
    assert len(backup["transactions"]) == 1

    # 3. Audit Logs recorded both exports
    logs = (await client.get("/api/v1/data/audit-logs", headers=auth_headers)).json()
    actions = {entry["action"] for entry in logs}
    assert "data.export_csv" in actions
    assert "data.export_json" in actions

    # 4. Permanent Account Deletion requires exact confirmation phrase & password
    bad_del = await client.request(
        "DELETE",
        "/api/v1/data/account",
        headers=auth_headers,
        json={"password": "StrongPassword123!", "confirm_phrase": "nope"},
    )
    assert bad_del.status_code == 400

    good_del = await client.request(
        "DELETE",
        "/api/v1/data/account",
        headers=auth_headers,
        json={"password": "StrongPassword123!", "confirm_phrase": "DELETE MY ACCOUNT"},
    )
    assert good_del.status_code == 204

    # Token should now fail because user was deleted
    me_after = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_after.status_code == 401


@pytest.mark.asyncio
async def test_rate_limiter_and_eval_suites() -> None:
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        allowed, _, _ = limiter.check("auth:127.0.0.1", limit=3, window_seconds=60)
        assert allowed is True
    allowed, remaining, retry_after = limiter.check("auth:127.0.0.1", limit=3, window_seconds=60)
    assert allowed is False
    assert remaining == 0
    assert retry_after >= 1

    # Verify all 5 LangSmith/offline evaluation suites score 100%
    results = await run_all_evals(sync_langsmith=False)
    assert len(results) == 5
    for r in results:
        assert r.score == 100.0, f"Eval suite {r.suite} scored {r.score}%: {r.details}"
