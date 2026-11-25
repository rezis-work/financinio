from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_email_preferences_previews_send_and_cron_dispatch(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # Seed account, transactions, recurring bill, and goal so both emails have rich data
    acc = (
        await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={
                "name": "BOG Main",
                "type": "checking",
                "currency": "GEL",
                "initial_balance": "4200.00",
            },
        )
    ).json()
    today = date.today()
    await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": acc["id"],
            "amount": "3500.00",
            "direction": "inflow",
            "occurred_at": (today - timedelta(days=2)).isoformat(),
            "merchant": "Remote Tech Payroll",
        },
    )
    await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": acc["id"],
            "amount": "145.00",
            "direction": "outflow",
            "occurred_at": (today - timedelta(days=1)).isoformat(),
            "merchant": "Carrefour Tbilisi",
        },
    )
    await client.post(
        "/api/v1/recurring",
        headers=auth_headers,
        json={
            "merchant_name": "MagtiCom Fiber",
            "amount": "45.00",
            "currency": "GEL",
            "direction": "outflow",
            "cadence": "monthly",
            "next_due_date": (today + timedelta(days=2)).isoformat(),
            "is_subscription": True,
        },
    )
    await client.post(
        "/api/v1/wealth/goals",
        headers=auth_headers,
        json={
            "name": "Emergency Fund",
            "goal_type": "emergency_fund",
            "target_amount": "10000.00",
            "current_amount": "7500.00",
            "monthly_contribution": "500.00",
        },
    )

    # 1. Preferences get + patch
    p0 = await client.get("/api/v1/emails/preferences", headers=auth_headers)
    assert p0.status_code == 200, p0.text
    assert p0.json()["email_weekly_briefing"] is True
    assert p0.json()["email_monthly_wrapped"] is True

    p1 = await client.patch(
        "/api/v1/emails/preferences",
        headers=auth_headers,
        json={"email_weekly_briefing": False},
    )
    assert p1.status_code == 200
    assert p1.json()["email_weekly_briefing"] is False

    # Re-enable weekly for dispatch test
    await client.patch(
        "/api/v1/emails/preferences",
        headers=auth_headers,
        json={"email_weekly_briefing": True},
    )

    # 2. Preview Weekly Briefing HTML
    wk = await client.get("/api/v1/emails/preview?digest_type=weekly", headers=auth_headers)
    assert wk.status_code == 200, wk.text
    wk_data = wk.json()
    assert "Luna Weekly Briefing" in wk_data["subject"]
    assert "MagtiCom Fiber" in wk_data["html"]
    assert "Open Briefing in Luna" in wk_data["html"]

    # 3. Preview Monthly CFO Wrapped HTML
    mo = await client.get("/api/v1/emails/preview?digest_type=monthly", headers=auth_headers)
    assert mo.status_code == 200, mo.text
    mo_data = mo.json()
    assert "CFO Wrapped" in mo_data["subject"]
    assert "Emergency Fund" in mo_data["html"]
    assert "Upload BOG PDF Statement" in mo_data["html"]

    # 4. Send test email via mocked Resend
    with patch("app.api.v1.emails.send_via_resend", new=AsyncMock(return_value="re_test_12345")):
        sent = await client.post(
            "/api/v1/emails/send-test",
            headers=auth_headers,
            json={"digest_type": "monthly"},
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["sent"] is True
        assert sent.json()["resend_email_id"] == "re_test_12345"

        # 5. Cron scheduled dispatch rejects wrong secret and accepts valid secret
        bad_cron = await client.post(
            "/api/v1/emails/dispatch-scheduled",
            headers={"X-Cron-Secret": "wrong"},
            json={"digest_type": "weekly"},
        )
        assert bad_cron.status_code == 403

        with patch("app.api.v1.emails.get_settings") as mock_settings:
            mock_settings.return_value.cron_secret = "super-secret-cron"
            ok_cron = await client.post(
                "/api/v1/emails/dispatch-scheduled",
                headers={"X-Cron-Secret": "super-secret-cron"},
                json={"digest_type": "weekly"},
            )
            assert ok_cron.status_code == 200, ok_cron.text
            assert ok_cron.json()["sent_count"] == 1
