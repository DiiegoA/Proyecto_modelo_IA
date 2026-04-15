from fastapi import APIRouter, Depends, File, UploadFile

from app.api.dependencies import get_knowledge_service, require_admin
from app.schemas.knowledge import KnowledgeSourceListResponse, ReindexRequest, ReindexResponse, UploadKnowledgeResponse
from app.services.knowledge import KnowledgeAdminService

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.post("/reindex", response_model=ReindexResponse, dependencies=[Depends(require_admin)])
def reindex_knowledge(
    payload: ReindexRequest,
    service: KnowledgeAdminService = Depends(get_knowledge_service),
) -> ReindexResponse:
    return service.reindex(mode=payload.mode)


@router.get("/sources", response_model=KnowledgeSourceListResponse, dependencies=[Depends(require_admin)])
def list_knowledge_sources(service: KnowledgeAdminService = Depends(get_knowledge_service)) -> KnowledgeSourceListResponse:
    return service.list_sources()


@router.post("/upload", response_model=UploadKnowledgeResponse, dependencies=[Depends(require_admin)])
async def upload_knowledge_document(
    file: UploadFile = File(...),
    service: KnowledgeAdminService = Depends(get_knowledge_service),
) -> UploadKnowledgeResponse:
    content = await file.read()
    return service.upload_document(file_name=file.filename or "documento.md", content=content)
