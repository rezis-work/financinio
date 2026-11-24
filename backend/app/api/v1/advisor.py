import json
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.checkpointer import checkpointer_manager
from app.ai.graphs.advisor_graph import _execute_action_in_neon, build_advisor_graph
from app.ai.observability import build_langgraph_config
from app.api.deps import get_current_user, get_vector_dep
from app.core.database import get_db
from app.models.advisor import ChatMessage, ChatThread, ProactiveInsight
from app.models.base import utcnow
from app.models.user import User
from app.schemas.advisor import (
    ActionDecisionRequest,
    ActionDecisionResponse,
    ChatMessageResponse,
    ChatSendRequest,
    ChatThreadCreate,
    ChatThreadDetailResponse,
    ChatThreadResponse,
    ProactiveInsightResponse,
    UserMemoryCreateRequest,
    UserMemoryItem,
)
from app.services.financial_health_service import compute_financial_health_profile
from app.services.insights_service import generate_proactive_insights
from app.services.quota_service import (
    TokenMeterCallbackHandler,
    enforce_ai_quota,
    record_ai_usage,
)
from app.services.vector_service import VectorMemoryBackend

router = APIRouter(prefix="/advisor", tags=["Luna AI Financial Advisor"])

NODE_STATUS_LABELS: dict[str, str] = {
    "recall_memory": "Recalling your financial preferences...",
    "supervisor_router": "Luna is routing your request...",
    "decision_advisor": "Senior CFP Advisor is evaluating your ratios & trade-offs...",
    "ledger_analyst": "Ledger Analyst is querying your accounts & cash flow...",
    "document_rag": "Searching your receipts & statements in Upstash Vector...",
    "wealth_strategist": "Wealth Strategist is running deterministic simulations...",
    "action_proposer": "Preparing action proposal for your approval...",
    "general": "Luna is analyzing...",
}


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


# --- Chat Threads ---


@router.get("/threads", response_model=list[ChatThreadResponse])
async def list_threads(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatThreadResponse]:
    rows = (
        await db.scalars(
            select(ChatThread)
            .where(ChatThread.user_id == current_user.id, ChatThread.is_archived.is_(False))
            .order_by(ChatThread.last_message_at.desc())
            .limit(30)
        )
    ).all()
    return [ChatThreadResponse.model_validate(t) for t in rows]


@router.post("/threads", response_model=ChatThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ChatThreadCreate | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatThreadResponse:
    title = (payload.title.strip() if payload and payload.title else None) or "New Conversation"
    thread = ChatThread(
        user_id=current_user.id,
        langgraph_thread_id=f"luna-{uuid4().hex}",
        title=title[:200],
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return ChatThreadResponse.model_validate(thread)


@router.get("/threads/{thread_id}", response_model=ChatThreadDetailResponse)
async def get_thread(
    thread_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatThreadDetailResponse:
    thread = await db.scalar(
        select(ChatThread)
        .options(selectinload(ChatThread.messages))
        .where(ChatThread.id == thread_id, ChatThread.user_id == current_user.id)
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found.")
    return ChatThreadDetailResponse(
        **ChatThreadResponse.model_validate(thread).model_dump(),
        messages=[ChatMessageResponse.model_validate(m) for m in thread.messages],
    )


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    thread = await db.scalar(
        select(ChatThread).where(ChatThread.id == thread_id, ChatThread.user_id == current_user.id)
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found.")
    await db.delete(thread)
    await db.commit()


# --- Streaming SSE Chat Endpoint ---


@router.post("/threads/{thread_id}/stream")
async def stream_advisor_reply(
    thread_id: UUID,
    payload: ChatSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> StreamingResponse:
    thread = await db.scalar(
        select(ChatThread).where(ChatThread.id == thread_id, ChatThread.user_id == current_user.id)
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found.")

    enforce_ai_quota(current_user)

    user_text = payload.message.strip()
    user_msg = ChatMessage(
        thread_id=thread.id,
        user_id=current_user.id,
        role="user",
        content=user_text,
    )
    db.add(user_msg)
    if thread.title == "New Conversation":
        thread.title = user_text[:64] + ("..." if len(user_text) > 64 else "")
    thread.last_message_at = utcnow()
    await db.commit()

    graph = build_advisor_graph(
        db=db,
        user=current_user,
        checkpointer=checkpointer_manager.saver,
        vector_service=vector_service,
    )
    token_meter = TokenMeterCallbackHandler()
    lg_config = build_langgraph_config(
        thread_id=thread.langgraph_thread_id,
        user_id=current_user.id,
        feature="advisor",
        extra_metadata={"chat_thread_id": str(thread.id)},
        extra_callbacks=[token_meter],
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        yield _sse_event("status", {"node": "start", "label": "Luna is analyzing your request..."})

        final_content = ""
        active_agent = "general"
        citations: list[dict] = []
        interrupt_action: dict | None = None

        try:
            async for chunk in graph.astream(
                {
                    "messages": [HumanMessage(content=user_text)],
                    "user_id": str(current_user.id),
                    "base_currency": current_user.base_currency,
                },
                config=lg_config,
                stream_mode="updates",
            ):
                if "__interrupt__" in chunk:
                    intr_tuple = chunk["__interrupt__"]
                    if intr_tuple:
                        intr_val = getattr(intr_tuple[0], "value", intr_tuple[0])
                        if isinstance(intr_val, dict):
                            interrupt_action = intr_val.get("action") or intr_val
                    continue

                for node_name, node_out in chunk.items():
                    if node_name in NODE_STATUS_LABELS:
                        yield _sse_event(
                            "status",
                            {"node": node_name, "label": NODE_STATUS_LABELS[node_name]},
                        )
                    if isinstance(node_out, dict):
                        if node_out.get("active_agent"):
                            active_agent = str(node_out["active_agent"])
                        if node_out.get("citations"):
                            citations = list(node_out["citations"])
                        msgs = node_out.get("messages") or []
                        if msgs:
                            last_msg = msgs[-1]
                            final_content = str(getattr(last_msg, "content", ""))

            if interrupt_action is not None:
                title = interrupt_action.get("title", "Proposed Financial Action")
                summary = interrupt_action.get(
                    "summary", "Please review and approve this change before I write to your ledger."
                )
                assistant_msg = ChatMessage(
                    thread_id=thread.id,
                    user_id=current_user.id,
                    role="assistant",
                    content=f"I've prepared **{title}** for your review:\n\n{summary}",
                    active_agent="action_proposer",
                    citations=[{"source": "HITL Approval Gate", "label": "Awaiting your confirmation"}],
                    pending_action=interrupt_action,
                    action_status="pending",
                )
                db.add(assistant_msg)
                thread.last_message_at = utcnow()
                await db.commit()
                await db.refresh(assistant_msg)

                await record_ai_usage(
                    db,
                    user=current_user,
                    feature="advisor_chat",
                    prompt_tokens=token_meter.prompt_tokens,
                    completion_tokens=token_meter.completion_tokens,
                    total_tokens=token_meter.total_tokens,
                    model_name=token_meter.model_name,
                    fallback_text=f"{user_text} {summary}",
                )

                msg_dto = ChatMessageResponse.model_validate(assistant_msg).model_dump(mode="json")
                yield _sse_event("action_required", {"message": msg_dto})
                yield _sse_event("done", {"message": msg_dto})
                return

            # Stream response in smooth chunks for responsive UI rendering
            words = final_content.split(" ")
            buf: list[str] = []
            for idx, word in enumerate(words):
                buf.append(word)
                if len(buf) >= 6 or idx == len(words) - 1:
                    piece = (" " if idx >= 6 else "") + " ".join(buf)
                    yield _sse_event("token", {"content": piece})
                    buf = []

            assistant_msg = ChatMessage(
                thread_id=thread.id,
                user_id=current_user.id,
                role="assistant",
                content=final_content,
                active_agent=active_agent,
                citations=citations,
                action_status="none",
            )
            db.add(assistant_msg)
            thread.last_message_at = utcnow()
            await db.commit()
            await db.refresh(assistant_msg)

            await record_ai_usage(
                db,
                user=current_user,
                feature="advisor_chat",
                prompt_tokens=token_meter.prompt_tokens,
                completion_tokens=token_meter.completion_tokens,
                total_tokens=token_meter.total_tokens,
                model_name=token_meter.model_name,
                fallback_text=f"{user_text} {final_content}",
            )

            msg_dto = ChatMessageResponse.model_validate(assistant_msg).model_dump(mode="json")
            yield _sse_event("done", {"message": msg_dto})
        except Exception as exc:
            yield _sse_event("error", {"detail": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- HITL Action Approval / Rejection ---


@router.post("/threads/{thread_id}/actions/{message_id}", response_model=ActionDecisionResponse)
async def decide_hitl_action(
    thread_id: UUID,
    message_id: UUID,
    payload: ActionDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> ActionDecisionResponse:
    thread = await db.scalar(
        select(ChatThread).where(ChatThread.id == thread_id, ChatThread.user_id == current_user.id)
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat thread not found.")

    msg = await db.scalar(
        select(ChatMessage).where(
            ChatMessage.id == message_id,
            ChatMessage.thread_id == thread.id,
            ChatMessage.user_id == current_user.id,
        )
    )
    if msg is None or msg.pending_action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pending action message not found."
        )
    if msg.action_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Action already processed ({msg.action_status}).",
        )

    graph = build_advisor_graph(
        db=db,
        user=current_user,
        checkpointer=checkpointer_manager.saver,
        vector_service=vector_service,
    )
    lg_config = build_langgraph_config(
        thread_id=thread.langgraph_thread_id,
        user_id=current_user.id,
        feature="advisor_hitl_decision",
        extra_metadata={"chat_thread_id": str(thread.id), "approved": payload.approved},
    )

    executed_result: dict | None = None
    followup_text = ""

    state_snap = await graph.aget_state(lg_config)
    if state_snap and state_snap.next:
        final_state = await graph.ainvoke(
            Command(
                resume={
                    "approved": payload.approved,
                    "override_params": payload.override_params or {},
                }
            ),
            config=lg_config,
        )
        executed_result = final_state.get("executed_result")
        msgs = final_state.get("messages") or []
        if msgs:
            followup_text = str(getattr(msgs[-1], "content", ""))
    else:
        # Fallback if checkpoint cleared between restarts
        if payload.approved:
            merged = {**msg.pending_action, **(payload.override_params or {})}
            executed_result = await _execute_action_in_neon(db, current_user, merged)
            followup_text = f"Approved and executed **{merged.get('title', 'action')}**."
        else:
            followup_text = "Canceled — nothing was changed in your account."

    msg.action_status = "executed" if payload.approved else "rejected"
    if followup_text:
        msg.content = f"{msg.content}\n\n---\n{followup_text}"
    thread.last_message_at = utcnow()
    await db.commit()
    await db.refresh(msg)

    return ActionDecisionResponse(
        message=ChatMessageResponse.model_validate(msg),
        executed_result=executed_result,
    )


# --- Long-Term User Memory (Upstash Vector) ---


@router.get("/memories", response_model=list[UserMemoryItem])
async def list_memories(
    current_user: User = Depends(get_current_user),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> list[UserMemoryItem]:
    facts = await vector_service.list_user_facts(current_user.id)
    return [UserMemoryItem(id=f.id, fact=f.fact, category=f.category, score=f.score) for f in facts]


@router.post("/memories", response_model=UserMemoryItem, status_code=status.HTTP_201_CREATED)
async def add_memory(
    payload: UserMemoryCreateRequest,
    current_user: User = Depends(get_current_user),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> UserMemoryItem:
    item = await vector_service.remember_user_fact(
        current_user.id, payload.fact, category=payload.category
    )
    return UserMemoryItem(id=item.id, fact=item.fact, category=item.category)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    vector_service: VectorMemoryBackend = Depends(get_vector_dep),
) -> None:
    await vector_service.delete_user_fact(current_user.id, memory_id)


# --- Financial Health Score (Senior CFP Diagnostic) ---


@router.get("/health-score")
async def get_financial_health_score(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await compute_financial_health_profile(db, current_user)


# --- Proactive AI Insights & Anomalies ---


@router.get("/insights", response_model=list[ProactiveInsightResponse])
async def list_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProactiveInsightResponse]:
    rows = (
        await db.scalars(
            select(ProactiveInsight)
            .where(
                ProactiveInsight.user_id == current_user.id,
                ProactiveInsight.is_dismissed.is_(False),
            )
            .order_by(ProactiveInsight.created_at.desc())
            .limit(20)
        )
    ).all()
    return [ProactiveInsightResponse.model_validate(r) for r in rows]


@router.post(
    "/insights/generate",
    response_model=list[ProactiveInsightResponse],
    status_code=status.HTTP_201_CREATED,
)
async def trigger_insights_generation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProactiveInsightResponse]:
    enforce_ai_quota(current_user)
    created = await generate_proactive_insights(db, current_user)
    digest_text = " ".join(i.summary for i in created[:2])
    await record_ai_usage(
        db,
        user=current_user,
        feature="proactive_insights",
        prompt_tokens=0,
        completion_tokens=0,
        fallback_text=digest_text,
    )
    return [ProactiveInsightResponse.model_validate(r) for r in created]


@router.patch("/insights/{insight_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_insight(
    insight_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    row = await db.scalar(
        select(ProactiveInsight).where(
            ProactiveInsight.id == insight_id, ProactiveInsight.user_id == current_user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insight not found.")
    row.is_dismissed = True
    await db.commit()
