import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from chat_nexus_mod_manager.database import get_session
from chat_nexus_mod_manager.models.chat import ChatMessage
from chat_nexus_mod_manager.schemas.chat import ChatMessageOut, ChatRequest

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/")
async def chat(data: ChatRequest, session: Session = Depends(get_session)) -> EventSourceResponse:
    session.add(ChatMessage(role="user", content=data.message))
    session.commit()

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        try:
            from chat_nexus_mod_manager.agents.orchestrator import run_agent

            async for event in run_agent(data.message, data.game_name):
                yield {"event": event["type"], "data": json.dumps(event["data"])}
        except ImportError:
            yield {
                "event": "token",
                "data": json.dumps({"content": "Chat agent not yet configured. Please set up your OpenAI API key in settings."}),
            }
        yield {"event": "done", "data": json.dumps({})}

    return EventSourceResponse(event_stream())


@router.get("/history", response_model=list[ChatMessageOut])
def chat_history(
    limit: int = 50, session: Session = Depends(get_session)
) -> list[ChatMessage]:
    return list(
        session.exec(
            select(ChatMessage).order_by(ChatMessage.created_at.desc()).limit(limit)  # type: ignore[arg-type]
        ).all()
    )
