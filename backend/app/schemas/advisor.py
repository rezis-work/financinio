from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: UUID
    role: Literal["user", "assistant"]
    content: str
    active_agent: str | None
    citations: list[dict[str, Any]]
    pending_action: dict[str, Any] | None
    action_status: str
    created_at: datetime


class ChatThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    langgraph_thread_id: str
    title: str
    last_message_at: datetime
    created_at: datetime


class ChatThreadDetailResponse(ChatThreadResponse):
    messages: list[ChatMessageResponse]


class ChatSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    web_search_mode: Literal["auto", "on", "off"] = "auto"


class ActionDecisionRequest(BaseModel):
    approved: bool
    override_params: dict[str, Any] | None = None


class ActionDecisionResponse(BaseModel):
    message: ChatMessageResponse
    executed_result: dict[str, Any] | None = None


class UserMemoryItem(BaseModel):
    id: str
    fact: str
    category: str
    score: float | None = None


class UserMemoryCreateRequest(BaseModel):
    fact: str = Field(min_length=3, max_length=500)
    category: str = Field(default="preference", max_length=48)


class ProactiveInsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    insight_type: str
    severity: str
    title: str
    summary: str
    data: dict[str, Any]
    is_read: bool
    is_dismissed: bool
    created_at: datetime
