from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session, get_health_service
from app.schemas.health import LiveHealthResponse, ReadyHealthResponse
from app.services.health import HealthService

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=LiveHealthResponse)
def live(service: HealthService = Depends(get_health_service)) -> LiveHealthResponse:
    return service.live()


@router.get("/ready", response_model=ReadyHealthResponse)
def ready(
    service: HealthService = Depends(get_health_service),
    session: Session = Depends(get_db_session),
) -> ReadyHealthResponse:
    return service.ready(session)
