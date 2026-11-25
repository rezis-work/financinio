from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.finance import Account, Category
from app.models.user import User
from app.schemas.voice import (
    ParsedVoiceTransactionResponse,
    VoiceParseRequest,
    VoiceSpeakRequest,
    VoiceTranscribeResponse,
)
from app.services.quota_service import enforce_ai_quota
from app.services.voice_service import (
    parse_voice_command,
    synthesize_speech_mp3,
    transcribe_audio_bytes,
)

router = APIRouter(prefix="/voice", tags=["Voice-to-Ledger & Talk to Luna"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_voice(
    file: UploadFile = File(...),
    language: Literal["auto", "en", "ka"] = Form(default="auto"),
    current_user: User = Depends(get_current_user),
) -> VoiceTranscribeResponse:
    """Transcribe English or Georgian voice audio for Voice-to-Ledger and Talk to Luna."""
    enforce_ai_quota(current_user)
    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Audio recording is empty."
        )
    if len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio recording exceeds 10 MB limit.",
        )

    try:
        transcript, model_used = await transcribe_audio_bytes(
            audio_bytes=raw,
            filename=file.filename or "voice.webm",
            language=language,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return VoiceTranscribeResponse(
        transcript=transcript,
        language=language,
        provider=model_used,
    )


@router.post("/parse-transaction", response_model=ParsedVoiceTransactionResponse)
async def parse_voice_to_ledger(
    payload: VoiceParseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ParsedVoiceTransactionResponse:
    """Parse spoken English or Georgian text into a ready-to-confirm transaction or Luna question."""
    accounts = list(
        (
            await db.scalars(
                select(Account)
                .where(Account.user_id == current_user.id, Account.is_archived.is_(False))
                .order_by(Account.created_at.asc())
            )
        ).all()
    )
    categories = list(
        (
            await db.scalars(
                select(Category)
                .where(Category.user_id == current_user.id)
                .order_by(Category.name.asc())
            )
        ).all()
    )

    return await parse_voice_command(
        transcript=payload.transcript,
        accounts=accounts,
        categories=categories,
        default_currency=current_user.base_currency,
    )


@router.post("/speak")
async def speak_luna_reply(
    payload: VoiceSpeakRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Synthesize a crisp spoken MP3 reply for Hands-Free Talk to Luna mode."""
    enforce_ai_quota(current_user)
    try:
        mp3_bytes = await synthesize_speech_mp3(text=payload.text, voice=payload.voice)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return Response(content=mp3_bytes, media_type="audio/mpeg")
