from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.rag.indexer import DocumentIndexer
from app.rag.loader import SUPPORTED_SUFFIXES


def get_docs_dir() -> Path:
    path = Path(settings.rag_docs_dir)
    if not path.is_absolute():
        path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件名")

    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持 {allowed} 文件",
        )
    return name


async def save_uploaded_doc(file: UploadFile) -> dict:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少文件名")

    filename = _safe_filename(file.filename)
    dest = get_docs_dir() / filename
    content = await file.read()

    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件必须是 UTF-8 文本",
        ) from exc

    dest.write_bytes(content)
    return {
        "filename": filename,
        "path": f"docs/{filename}",
        "size": len(content),
    }


def index_knowledge_base(db: Session, *, rebuild: bool = False) -> dict:
    try:
        stats = DocumentIndexer(db).index_all(rebuild=rebuild)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return stats
