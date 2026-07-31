from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse, success
from app.schemas.docs import (
    AskRequest,
    IndexStatsData,
    SearchRequest,
    SearchResultData,
    UploadDocData,
)
from app.services.ask import ask_knowledge_base_stream
from app.services.docs import index_knowledge_base, save_uploaded_doc, search_knowledge_base

router = APIRouter()


@router.post("/upload", response_model=ApiResponse[UploadDocData])
async def upload_document(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> ApiResponse[UploadDocData]:
    data = await save_uploaded_doc(file)
    return success(UploadDocData(**data), message="文件上传成功")


@router.post("/index", response_model=ApiResponse[IndexStatsData])
def index_documents(
    path: str | None = Query(
        None,
        description="指定单个文件路径，如 docs/笔记.md；不传则索引整个 docs 目录",
    ),
    rebuild: bool = Query(False, description="是否强制重建（单文件时强制重写该文件）"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[IndexStatsData]:
    stats = index_knowledge_base(db, path=path, rebuild=rebuild)
    message = "单文件知识库更新完成" if path else "知识库更新完成"
    return success(IndexStatsData(**stats), message=message)


@router.post("/search", response_model=ApiResponse[SearchResultData])
def search_documents(
    payload: SearchRequest,
    _: User = Depends(get_current_user),
) -> ApiResponse[SearchResultData]:
    data = search_knowledge_base(
        query=payload.query,
        top_k=payload.top_k,
        source_path=payload.source_path,
        title=payload.title,
        updated_at=payload.updated_at,
    )
    return success(SearchResultData(**data), message="检索完成")


@router.post("/ask")
async def ask_documents(
    payload: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """SSE：rewrite → retrieve → answer（LangGraph），并写入 ask_logs。"""

    async def event_generator():
        async for frame in ask_knowledge_base_stream(
            query=payload.query,
            top_k=payload.top_k,
            source_path=payload.source_path,
            title=payload.title,
            updated_at=payload.updated_at,
            user_id=current_user.id,
            db=db,
        ):
            yield frame

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
