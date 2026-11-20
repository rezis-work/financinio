import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_refresh_and_seed_categories(client: AsyncClient) -> None:
    # 1. Register
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@financinio.app",
            "password": "SuperSecretPassword!",
            "full_name": "Bob Investor",
            "base_currency": "EUR",
        },
    )
    assert reg.status_code == 201
    data = reg.json()
    assert data["user"]["email"] == "bob@financinio.app"
    assert data["user"]["base_currency"] == "EUR"
    access = data["access_token"]
    refresh = data["refresh_token"]

    # 2. Default categories seeded automatically
    cats = await client.get("/api/v1/categories", headers={"Authorization": f"Bearer {access}"})
    assert cats.status_code == 200
    assert len(cats.json()) >= 15

    # 3. Refresh token rotation
    ref = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert ref.status_code == 200
    new_refresh = ref.json()["refresh_token"]
    assert new_refresh != refresh

    # Old refresh token must now be revoked
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert reused.status_code == 401

    # 4. Login
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@financinio.app", "password": "SuperSecretPassword!"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["full_name"] == "Bob Investor"
