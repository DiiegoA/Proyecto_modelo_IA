from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_thread_service
from app.clients.oraculo_api import AuthenticatedUser
from app.schemas.thread import ThreadResponse
from app.services.thread import ThreadService

router = APIRouter(prefix="/threads", tags=["Threads"])


@router.get("/{thread_id}", response_model=ThreadResponse)
def get_thread(
    thread_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    service: ThreadService = Depends(get_thread_service),
) -> ThreadResponse:
    return service.get_thread(thread_id=thread_id, user_id=current_user.id)
