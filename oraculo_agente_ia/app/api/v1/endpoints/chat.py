from fastapi import APIRouter, Depends
from sse_starlette import EventSourceResponse

from app.api.dependencies import get_agent_service, get_current_user
from app.clients.oraculo_api import AuthenticatedUser
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent import AgentService

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/invoke", response_model=ChatResponse)
def invoke_chat(
    payload: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> ChatResponse:
    return service.invoke(payload=payload, current_user=current_user)


@router.post("/stream")
def stream_chat(
    payload: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> EventSourceResponse:
    async def event_generator():
        for event in service.stream(payload=payload, current_user=current_user):
            yield {"event": event.event, "data": event.model_dump_json()}

    return EventSourceResponse(event_generator())
