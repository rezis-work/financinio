from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.voice_service import clean_markdown_for_speech


def test_clean_markdown_for_speech() -> None:
    md = (
        "### Market Verdict\n\n"
        "**NVDA** is trading at `$153.50` with a **Buy** signal.\n\n"
        "| Symbol | Price |\n| :--- | ---: |\n| NVDA | 153.50 |\n\n"
        "Check [MyHome](https://myhome.ge/en) for details."
    )
    spoken = clean_markdown_for_speech(md)
    assert "###" not in spoken
    assert "| NVDA |" not in spoken
    assert "https://" not in spoken
    assert "NVDA is trading at $153.50" in spoken
    assert "Check MyHome for details." in spoken


@pytest.mark.asyncio
async def test_voice_to_ledger_english_georgian_and_ask_luna(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    with patch("app.services.voice_service.get_chat_model", return_value=None):
        # Create a Bank of Georgia GEL account so account matching works
        acc = (
            await client.post(
                "/api/v1/accounts",
                headers=auth_headers,
                json={
                    "name": "BOG Main Card",
                    "type": "checking",
                    "currency": "GEL",
                    "initial_balance": "1500.00",
                    "institution": "Bank of Georgia",
                },
            )
        ).json()

        # 1. English expense voice command
        r1 = await client.post(
            "/api/v1/voice/parse-transaction",
            headers=auth_headers,
            json={"transcript": "Spent 18 lari at Entree on coffee from BOG"},
        )
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["intent"] == "log_transaction"
        assert d1["amount"] == "18.00"
        assert d1["currency"] == "GEL"
        assert d1["direction"] == "outflow"
        assert "Entree" in d1["merchant"]
        assert d1["account_id"] == acc["id"]
        assert d1["category_id"] is not None

        # 2. Georgian expense voice command (yesterday)
        r2 = await client.post(
            "/api/v1/voice/parse-transaction",
            headers=auth_headers,
            json={"transcript": "გუშინ დავხარჯე 45 ლარი კარფურში BOG ბარათით", "language": "ka"},
        )
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["intent"] == "log_transaction"
        assert d2["amount"] == "45.00"
        assert d2["currency"] == "GEL"
        assert d2["occurred_at"] == (date.today() - timedelta(days=1)).isoformat()
        assert d2["account_id"] == acc["id"]

        # 3. Question intent routes to Ask Luna
        r3 = await client.post(
            "/api/v1/voice/parse-transaction",
            headers=auth_headers,
            json={
                "transcript": "Hey Luna, what's NVDA doing today and how much safe-to-spend do I have left?"
            },
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["intent"] == "ask_luna"


@pytest.mark.asyncio
async def test_voice_transcribe_and_speak_endpoints(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    with (
        patch(
            "app.api.v1.voice.transcribe_audio_bytes",
            new=AsyncMock(return_value=("Spent 22 lari at Wolt", "gpt-4o-mini-transcribe")),
        ),
        patch(
            "app.api.v1.voice.synthesize_speech_mp3",
            new=AsyncMock(return_value=b"ID3fake-mp3-bytes"),
        ),
    ):
        tr = await client.post(
            "/api/v1/voice/transcribe",
            headers=auth_headers,
            files={"file": ("voice.webm", b"fake-audio-payload", "audio/webm")},
            data={"language": "auto"},
        )
        assert tr.status_code == 200, tr.text
        assert tr.json()["transcript"] == "Spent 22 lari at Wolt"

        sp = await client.post(
            "/api/v1/voice/speak",
            headers=auth_headers,
            json={"text": "### Verdict\nYou have 400 GEL safe to spend this week.", "voice": "nova"},
        )
        assert sp.status_code == 200
        assert sp.headers["content-type"].startswith("audio/mpeg")
        assert sp.content == b"ID3fake-mp3-bytes"
