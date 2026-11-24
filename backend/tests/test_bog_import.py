from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.ai.parsers.bog_pdf import (
    _reconcile_bog_statement,
    is_bog_statement,
    parse_bog_pdf,
    parse_bog_text,
)
from app.services.ledger_service import compute_transaction_fingerprint

# Exact structure & Georgian content from a real Bank of Georgia (BOG) Internet Bank PDF export
SAMPLE_BOG_STATEMENT_TEXT = """ანგარიშიდან ამონაწერი
ანგარიშის მფლობელი: კარანაძე რევაზი
ბარათი: Student Card (4592)
ამონაწერის გაცემის თარიღი: 24/11/2026
ამონაწერის პერიოდი: 16/11/2026 - 23/11/2026
ანგარიშის ნომერი: GE54BG0000000103288154
16/11/2026
23/11/2026 საბოლოო ნაშთი:
საწყისი ნაშთი:
GEL
9.35
3.71
USD
1.17
1.17
EUR
0
0
GBP
0.00
0.00
თარიღი დანიშნულება GEL USD EUR GBP
17/11/2026 ჩარიცხვა - თანხა: GEL42.76; გადმომრიცხავი: კარანაძე რევაზი;
ანგარიში: GE08BG0000000548282690GEL; ბანკი: სს "საქართველოს
ბანკი" BAGAGE22; დანიშნულება: პირადი გადარიცხვა
42.76
18/11/2026 გადახდა - თანხა: GEL4.80; ობიექტი: LTD KEEPZ.ME*YANDEX GO,
Georgia; MCC:4121; თარიღი: 17/11/2026 17:53; ბარათის No: ****4592;
გადახდის ოპერაციის თანხა და ვალუტა: 4.80 GEL
-4.8
18/11/2026 გადახდა - თანხა: GEL8.60; ობიექტი: LTD KEEPZ.ME*YANDEX GO,
Georgia; MCC:4121; თარიღი: 17/11/2026 19:31; ბარათის No: ****4592;
გადახდის ოპერაციის თანხა და ვალუტა: 8.60 GEL
-8.6
19/11/2026 გადარიცხვა - თანხა: GEL34.00; მიმღები: კარანაძე რევაზი; ანგარიში:
GE30BG0000000613715972GEL; ბანკი: სს "საქართველოს ბანკი"
BAGAGE22; დანიშნულება: საკრედიტო ბარათზე გადარიცხვა
-34.0
23/11/2026 გადახდა - თანხა GEL1.00; ანგარიშის მომსახურების საკომისიო,
ანგარიშის No: GE28BG0000000569520286
-1.0
შემოსული თანხების ჯამი:
გასული თანხების ჯამი:
42.76
48.4
0
0
0
0
0.00
0.00
გვ. 1 (სულ 1 გვ.) -კონფიდენციალური-
"""


def test_bog_statement_detection_and_exact_parsing() -> None:
    assert is_bog_statement(SAMPLE_BOG_STATEMENT_TEXT) is True
    assert is_bog_statement("Chase Bank Monthly Statement\nOpening Balance $500") is False

    rows, meta = parse_bog_text(SAMPLE_BOG_STATEMENT_TEXT, default_currency="GEL")
    assert len(rows) == 5
    assert meta.iban == "GE54BG0000000103288154"
    assert meta.period == "16/11/2026 - 23/11/2026"
    assert meta.opening_balances["GEL"] == Decimal("9.35")
    assert meta.closing_balances["GEL"] == Decimal("3.71")
    assert meta.opening_balances["USD"] == Decimal("1.17")
    assert meta.closing_balances["USD"] == Decimal("1.17")

    # Row 1: Incoming personal transfer
    assert rows[0].occurred_at == date(2026, 11, 17)
    assert rows[0].direction == "inflow"
    assert rows[0].amount == Decimal("42.76")
    assert rows[0].currency == "GEL"
    assert "კარანაძე რევაზი" in rows[0].merchant_clean
    assert rows[0].raw_payload["bog_category_hint"] == "Internal Transfer"

    # Row 2 & 3: Yandex Go card payments (MCC 4121 -> Transportation & Transit)
    assert rows[1].occurred_at == date(2026, 11, 18)
    assert rows[1].direction == "outflow"
    assert rows[1].amount == Decimal("4.80")
    assert rows[1].merchant_clean == "Yandex Go"
    assert rows[1].raw_payload["mcc"] == "4121"
    assert rows[1].raw_payload["bog_category_hint"] == "Transportation & Transit"

    assert rows[2].occurred_at == date(2026, 11, 18)
    assert rows[2].direction == "outflow"
    assert rows[2].amount == Decimal("8.60")
    assert rows[2].merchant_clean == "Yandex Go"
    assert rows[1].merchant_raw != rows[2].merchant_raw  # distinct timestamps preserved

    # Row 4: Outgoing credit card transfer
    assert rows[3].occurred_at == date(2026, 11, 19)
    assert rows[3].direction == "outflow"
    assert rows[3].amount == Decimal("34.00")
    assert "საკრედიტო ბარათზე გადარიცხვა" in rows[3].merchant_clean
    assert rows[3].raw_payload["bog_category_hint"] == "Internal Transfer"

    # Row 5: Bank account maintenance fee (no colon after თანხა)
    assert rows[4].occurred_at == date(2026, 11, 23)
    assert rows[4].direction == "outflow"
    assert rows[4].amount == Decimal("1.00")
    assert "საკომისიო" in rows[4].merchant_clean
    assert rows[4].raw_payload["bog_category_hint"] == "Taxes & Fees"

    # Multi-currency reconciliation: 9.35 + 42.76 - 48.40 == 3.71 exact
    reconciled, note = _reconcile_bog_statement(rows, meta)
    assert reconciled is True
    assert "3.71" in note
    assert "5 transactions" in note


def test_georgian_unicode_fingerprints_do_not_collide() -> None:
    acc_id = uuid4()
    fp1 = compute_transaction_fingerprint(
        account_id=acc_id,
        occurred_at=date(2026, 11, 23),
        amount=Decimal("10.00"),
        direction="outflow",
        merchant_raw="ნიკორა სუპერმარკეტი",
    )
    fp2 = compute_transaction_fingerprint(
        account_id=acc_id,
        occurred_at=date(2026, 11, 23),
        amount=Decimal("10.00"),
        direction="outflow",
        merchant_raw="კარფური თბილისი",
    )
    assert fp1 != fp2


@pytest.mark.asyncio
async def test_dedicated_bog_pdf_import_endpoint_hitl_and_dedupe(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # Create a GEL Bank of Georgia checking account with opening balance 9.35
    acc = (
        await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={
                "name": "BOG Student Card",
                "type": "checking",
                "currency": "GEL",
                "initial_balance": "9.35",
                "institution": "Bank of Georgia",
            },
        )
    ).json()

    # 1. Reject non-PDF on dedicated /imports/bog endpoint
    bad_ext = await client.post(
        "/api/v1/imports/bog",
        headers=auth_headers,
        data={"account_id": acc["id"]},
        files={"file": ("statement.csv", b"date,amount\n2026-11-17,10\n", "text/csv")},
    )
    assert bad_ext.status_code == 400

    # 2. Upload BOG PDF offline (no LLM needed!)
    fake_pdf_bytes = b"%PDF-1.4\n%BOG-TEST\n%%EOF"
    rows, meta = parse_bog_text(SAMPLE_BOG_STATEMENT_TEXT, default_currency="GEL")
    reconciled, note = _reconcile_bog_statement(rows, meta)

    with (
        patch("app.ai.graphs.ingestion_graph.get_chat_model", return_value=None),
        patch(
            "app.ai.graphs.ingestion_graph.parse_bog_pdf",
            return_value=(rows, SAMPLE_BOG_STATEMENT_TEXT, reconciled, note),
        ),
    ):
        up = await client.post(
            "/api/v1/imports/bog",
            headers=auth_headers,
            data={"account_id": acc["id"]},
            files={"file": ("bog_statement_nov2026.pdf", fake_pdf_bytes, "application/pdf")},
        )
        assert up.status_code == 201, up.text
        batch = up.json()
        assert batch["doc_type"] == "bog_pdf"
        assert batch["status"] == "needs_review"
        assert batch["total_rows"] == 5
        assert batch["duplicate_rows"] == 0
        assert batch["balance_reconciled"] is True
        assert "3.71" in (batch["reconciliation_note"] or "")

        staged = batch["staged_transactions"]
        assert len(staged) == 5
        assert staged[1]["merchant_clean"] == "Yandex Go"
        assert staged[1]["categorization_source"] == "bog_mcc"
        assert staged[4]["categorization_source"] == "bog_rule"

        # 3. Approve & Commit all 5 rows to Neon ledger
        commit = await client.post(
            f"/api/v1/imports/{batch['id']}/commit",
            headers=auth_headers,
            json={
                "decisions": [
                    {
                        "staged_id": s["id"],
                        "user_approved": True,
                        "merchant_clean": s["merchant_clean"],
                        "category_id": s["suggested_category_id"],
                    }
                    for s in staged
                ],
                "skip_duplicates": True,
                "learn_from_edits": True,
            },
        )
        assert commit.status_code == 200, commit.text
        assert commit.json()["committed_rows"] == 5

        # Account balance must now equal exact BOG closing balance: 9.35 + 42.76 - 48.40 = 3.71!
        accounts = (await client.get("/api/v1/accounts", headers=auth_headers)).json()
        bog_acc = next(a for a in accounts if a["id"] == acc["id"])
        assert bog_acc["current_balance"] == "3.71"

        # 4. Re-upload same BOG PDF -> all 5 rows detected as duplicates
        up2 = await client.post(
            "/api/v1/imports/bog",
            headers=auth_headers,
            data={"account_id": acc["id"]},
            files={"file": ("bog_statement_nov2026.pdf", fake_pdf_bytes, "application/pdf")},
        )
        assert up2.status_code == 201
        assert up2.json()["duplicate_rows"] == 5


def test_parse_bog_pdf_strict_rejects_non_bog_text() -> None:
    with patch("app.ai.parsers.bog_pdf._extract_bog_via_pdfplumber", side_effect=RuntimeError("no pdf")):
        with pytest.raises(ValueError, match="Bank of Georgia"):
            parse_bog_pdf(b"not a bog pdf", strict=True)
