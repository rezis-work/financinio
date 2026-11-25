from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class VoiceTranscribeResponse(BaseModel):
    transcript: str
    language: str = "auto"
    provider: str = "openai"


class VoiceParseRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=1000)
    language: Literal["auto", "en", "ka"] = "auto"


class ParsedVoiceTransactionResponse(BaseModel):
    intent: Literal["log_transaction", "ask_luna"] = "log_transaction"
    transcript: str
    amount: Decimal | None = None
    currency: str = "GEL"
    direction: Literal["inflow", "outflow"] = "outflow"
    merchant: str = ""
    occurred_at: date
    account_id: UUID | None = None
    account_name: str | None = None
    category_id: UUID | None = None
    category_name: str | None = None
    notes: str | None = None
    confidence: float = 0.85


class VoiceSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: Literal["nova", "alloy", "shimmer", "echo", "onyx"] = "nova"
