from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.rag.chroma_store import get_chroma_store
from app.rag.embedder import get_embedder
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


def resolve_docs_file(path: str) -> Path:
    """将 docs/xxx.md 或 xxx.md 解析为 docs 目录内的真实文件路径。"""
    if not path or not path.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少文件路径")

    docs_dir = get_docs_dir()
    raw = path.strip().replace("\\", "/")
    candidate = Path(raw)

    if candidate.is_absolute():
        file_path = candidate
    elif raw.startswith("docs/"):
        file_path = docs_dir.parent / raw
    else:
        file_path = docs_dir / Path(raw).name

    file_path = file_path.resolve()
    docs_root = docs_dir.resolve()
    try:
        file_path.relative_to(docs_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能索引 docs 目录下的文件",
        ) from exc

    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"文件不存在: {raw}")

    if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持 {allowed} 文件",
        )
    return file_path


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


def index_knowledge_base(
    db: Session,
    *,
    path: str | None = None,
    rebuild: bool = False,
) -> dict:
    try:
        indexer = DocumentIndexer(db)
        if path:
            stats = indexer.index_file(resolve_docs_file(path), force=rebuild)
        else:
            stats = indexer.index_all(rebuild=rebuild)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return stats


def _build_chroma_where(
    *,
    source_path: str | None = None,
    title: str | None = None,
    updated_at: str | None = None,
) -> dict | None:
    clauses: list[dict] = []
    if source_path and source_path.strip():
        clauses.append({"source_path": {"$eq": source_path.strip().replace("\\", "/")}})
    if title and title.strip():
        clauses.append({"title": {"$eq": title.strip()}})
    if updated_at and updated_at.strip():
        clauses.append({"updated_at": {"$eq": updated_at.strip()}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def search_knowledge_base(
    *,
    query: str,
    top_k: int = 5,
    source_path: str | None = None,
    title: str | None = None,
    updated_at: str | None = None,
) -> dict:
    text = query.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="检索关键字不能为空")

    embedding = get_embedder().embed_query(text)
    where = _build_chroma_where(
        source_path=source_path,
        title=title,
        updated_at=updated_at,
    )
    hits = get_chroma_store().query(
        embedding,
        n_results=top_k,
        where=where,
    )

    normalized_hits = []
    for hit in hits:
        meta = hit.get("metadata") or {}
        chunk_index = meta.get("chunk_index")
        document_id = meta.get("document_id")
        chunk_id = meta.get("chunk_id")
        normalized_hits.append(
            {
                "chroma_id": hit["chroma_id"],
                "content": hit.get("content") or "",
                "distance": hit.get("distance"),
                "score": hit.get("score"),
                # Chroma 历史数据可能是 int，响应 schema 统一为 str
                "document_id": None if document_id is None else str(document_id),
                "chunk_id": None if chunk_id is None else str(chunk_id),
                "chunk_index": int(chunk_index) if chunk_index is not None else None,
                "source_path": meta.get("source_path"),
                "title": meta.get("title"),
                "updated_at": meta.get("updated_at") or None,
            }
        )

    return {
        "query": text,
        "total": len(normalized_hits),
        "hits": normalized_hits,
    }
