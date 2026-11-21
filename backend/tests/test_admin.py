from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.core.config import get_settings


@pytest.mark.asyncio
async def test_admin_rbac_fixed_token_quota_and_unlimited_grant(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "admin@financinio.app")
    monkeypatch.setenv("DEFAULT_USER_AI_TOKEN_LIMIT", "100")
    get_settings.cache_clear()

    try:
        # 1. Register an Admin (auto-promoted via ADMIN_EMAILS) and a Standard User
        admin_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "admin@financinio.app",
                "password": "AdminPassword123!",
                "full_name": "Platform Admin",
                "base_currency": "USD",
            },
        )
        assert admin_reg.status_code == 201, admin_reg.text
        admin_data = admin_reg.json()
        assert admin_data["user"]["role"] == "admin"
        assert admin_data["user"]["has_unlimited_ai"] is True
        admin_headers = {"Authorization": f"Bearer {admin_data['access_token']}"}

        user_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "standard@financinio.app",
                "password": "UserPassword123!",
                "full_name": "Standard User",
                "base_currency": "USD",
            },
        )
        assert user_reg.status_code == 201
        user_data = user_reg.json()
        user_id = user_data["user"]["id"]
        assert user_data["user"]["role"] == "user"
        assert user_data["user"]["has_unlimited_ai"] is False
        assert user_data["user"]["ai_token_limit"] == 100
        user_headers = {"Authorization": f"Bearer {user_data['access_token']}"}

        # 2. Standard user is blocked (403) from Admin routes
        forbid = await client.get("/api/v1/admin/overview", headers=user_headers)
        assert forbid.status_code == 403

        # 3. Admin views overview & user list
        ov = await client.get("/api/v1/admin/overview", headers=admin_headers)
        assert ov.status_code == 200
        assert ov.json()["total_users"] == 2
        assert ov.json()["unlimited_users"] == 1

        users_list = (await client.get("/api/v1/admin/users", headers=admin_headers)).json()
        assert len(users_list) == 2

        # 4. Standard user uses AI until hitting the 100-token cap -> receives HTTP 402
        with patch("app.ai.graphs.advisor_graph.get_chat_model", return_value=None):
            th = (
                await client.post("/api/v1/advisor/threads", headers=user_headers, json={})
            ).json()

            # Lower user limit to 10 tokens via admin to trigger cap after 1st turn
            cap_resp = await client.patch(
                f"/api/v1/admin/users/{user_id}/access",
                headers=admin_headers,
                json={"ai_token_limit": 10},
            )
            assert cap_resp.status_code == 200
            assert cap_resp.json()["ai_token_limit"] == 10

            # First chat succeeds and meters tokens (>10 tokens)
            r1 = await client.post(
                f"/api/v1/advisor/threads/{th['id']}/stream",
                headers=user_headers,
                json={"message": "How much did I spend this month on groceries and dining?"},
            )
            assert r1.status_code == 200

            # Second chat is blocked with 402 Payment Required because fixed cap exceeded!
            r2 = await client.post(
                f"/api/v1/advisor/threads/{th['id']}/stream",
                headers=user_headers,
                json={"message": "Show me my accounts"},
            )
            assert r2.status_code == 402

            # 5. Admin grants Full Access (Unlimited Tokens) -> user immediately unblocked!
            grant = await client.patch(
                f"/api/v1/admin/users/{user_id}/access",
                headers=admin_headers,
                json={"has_unlimited_ai": True},
            )
            assert grant.status_code == 200
            assert grant.json()["has_unlimited_ai"] is True

            r3 = await client.post(
                f"/api/v1/advisor/threads/{th['id']}/stream",
                headers=user_headers,
                json={"message": "Show me my accounts now"},
            )
            assert r3.status_code == 200

        # 6. Admin self-demotion guard works
        self_demote = await client.patch(
            f"/api/v1/admin/users/{admin_data['user']['id']}/access",
            headers=admin_headers,
            json={"role": "user"},
        )
        assert self_demote.status_code == 400

        # 7. Admin suspends standard user -> standard user blocked (403)
        suspend = await client.patch(
            f"/api/v1/admin/users/{user_id}/access",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert suspend.status_code == 200
        assert suspend.json()["is_active"] is False

        blocked_me = await client.get("/api/v1/auth/me", headers=user_headers)
        assert blocked_me.status_code == 403
    finally:
        get_settings.cache_clear()
