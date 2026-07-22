from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse, success
from app.schemas.docs import IndexStatsData, UploadDocData
from app.services.docs import index_knowledge_base, save_uploaded_doc

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
    rebuild: bool = Query(False, description="是否清空后全量重建"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[IndexStatsData]:
    stats = index_knowledge_base(db, rebuild=rebuild)
    return success(IndexStatsData(**stats), message="知识库更新完成")
