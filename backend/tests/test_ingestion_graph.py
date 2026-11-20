import pytest
from httpx import AsyncClient

from tests.conftest import InMemoryVectorService


@pytest.mark.asyncio
async def test_langgraph_csv_ingestion_hitl_dedupe_and_vector_learning(
    client: AsyncClient,
    auth_headers: dict[str, str],
    fake_vector: InMemoryVectorService,
) -> None:
    # 1. Create an account
    acc = (
        await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={
                "name": "Everyday Checking",
                "type": "checking",
                "currency": "USD",
                "initial_balance": "1000.00",
            },
        )
    ).json()

    cats = (await client.get("/api/v1/categories", headers=auth_headers)).json()
    dining_cat = next(c for c in cats if c["name"] == "Dining & Coffee")
    subs_cat = next(c for c in cats if c["name"] == "Subscriptions & Software")

    # 2. Add a Tier-1 deterministic rule for "BLUE BOTTLE"
    rule_resp = await client.post(
        "/api/v1/categories/rules",
        headers=auth_headers,
        json={
            "match_pattern": "BLUE BOTTLE",
            "match_type": "contains",
            "category_id": dining_cat["id"],
            "merchant_override": "Blue Bottle Coffee",
            "priority": 10,
        },
    )
    assert rule_resp.status_code == 201

    # 3. Upload a CSV bank statement (triggers LangGraph parse -> dedupe -> categorize -> interrupt)
    csv_content = (
        b"Date,Description,Amount\n"
        b"2026-11-01,BLUE BOTTLE COFFEE #12,-6.75\n"
        b"2026-11-02,ACME CLOUD TOOLING*99A1,-29.00\n"
        b"2026-11-03,GUSTO PAYROLL DEPOSIT,3500.00\n"
    )

    upload = await client.post(
        "/api/v1/imports/upload",
        headers=auth_headers,
        data={"account_id": acc["id"]},
        files={"file": ("november_statement.csv", csv_content, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    batch = upload.json()
    assert batch["status"] == "needs_review"
    assert batch["total_rows"] == 3
    assert batch["duplicate_rows"] == 0

    staged = batch["staged_transactions"]
    assert len(staged) == 3

    # Row 0 matched Tier-1 rule!
    assert staged[0]["categorization_source"] == "rule"
    assert staged[0]["merchant_clean"] == "Blue Bottle Coffee"
    assert staged[0]["suggested_category_id"] == dining_cat["id"]

    # Row 1 ("ACME CLOUD TOOLING*99A1") was unknown -> user corrects it to Subscriptions in HITL review
    acme_row = staged[1]
    commit = await client.post(
        f"/api/v1/imports/{batch['id']}/commit",
        headers=auth_headers,
        json={
            "decisions": [
                {
                    "staged_id": acme_row["id"],
                    "user_approved": True,
                    "merchant_clean": "Acme Cloud",
                    "category_id": subs_cat["id"],
                }
            ],
            "skip_duplicates": True,
            "learn_from_edits": True,
        },
    )
    assert commit.status_code == 200, commit.text
    committed_batch = commit.json()
    assert committed_batch["status"] == "committed"
    assert committed_batch["committed_rows"] == 3

    # Account balance updated: 1000 - 6.75 - 29.00 + 3500 = 4464.25
    accounts = (await client.get("/api/v1/accounts", headers=auth_headers)).json()
    assert accounts[0]["current_balance"] == "4464.25"

    # 4. Upload a second CSV containing:
    #    - One duplicate of the earlier payroll deposit (should be flagged duplicate!)
    #    - A new charge from "ACME CLOUD TOOLING*99A1" (should now auto-match Upstash Vector memory!)
    csv_second = (
        b"Date,Description,Amount\n"
        b"2026-11-03,GUSTO PAYROLL DEPOSIT,3500.00\n"
        b"2026-11-18,ACME CLOUD TOOLING*99A1,-29.00\n"
    )

    upload2 = await client.post(
        "/api/v1/imports/upload",
        headers=auth_headers,
        data={"account_id": acc["id"]},
        files={"file": ("november_part2.csv", csv_second, "text/csv")},
    )
    assert upload2.status_code == 201, upload2.text
    batch2 = upload2.json()
    assert batch2["duplicate_rows"] == 1
    assert batch2["staged_transactions"][0]["is_duplicate"] is True
    assert batch2["staged_transactions"][1]["categorization_source"] == "vector"
    assert batch2["staged_transactions"][1]["merchant_clean"] == "Acme Cloud"
    assert batch2["staged_transactions"][1]["suggested_category_id"] == subs_cat["id"]
