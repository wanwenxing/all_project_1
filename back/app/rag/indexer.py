from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.rag.chroma_store import ChromaStore, get_chroma_store
from app.rag.embedder import BGEEmbedder, get_embedder
from app.rag.loader import load_documents, parse_document_file
from app.rag.splitter import split_document
from app.rag.types import ParsedDocument


class DocumentIndexer:
    def __init__(
        self,
        db: Session,
        chroma_store: ChromaStore | None = None,
        embedder: BGEEmbedder | None = None,
    ) -> None:
        self.db = db
        self.chroma = chroma_store or get_chroma_store()
        self.embedder = embedder or get_embedder()

    def index_all(self, docs_dir: str | None = None, rebuild: bool = False) -> dict:
        stats = {"indexed": 0, "skipped": 0, "removed": 0, "chunks": 0}

        if rebuild:
            self._reset_all(stats)

        parsed_docs = load_documents(docs_dir or settings.rag_docs_dir)
        current_paths = {doc.source_path for doc in parsed_docs}

        # 从数据库中删除磁盘上已经不存在的文档
        for source_path in self._list_document_paths():
            if source_path not in current_paths:
                self._remove_document_by_path(source_path)
                stats["removed"] += 1

        for parsed_doc in parsed_docs:
            chunk_count = self._index_document(parsed_doc, force=rebuild)
            if chunk_count == 0:
                stats["skipped"] += 1
            else:
                stats["indexed"] += 1
                stats["chunks"] += chunk_count

        return stats

    def index_file(self, file_path: str | Path, *, force: bool = False) -> dict:
        """只索引指定单个文件，不扫描整个 docs 目录。"""
        stats = {"indexed": 0, "skipped": 0, "removed": 0, "chunks": 0}
        docs_dir = Path(settings.rag_docs_dir).resolve()
        parsed_doc = parse_document_file(Path(file_path), docs_dir)
        chunk_count = self._index_document(parsed_doc, force=force)
        if chunk_count == 0:
            stats["skipped"] = 1
        else:
            stats["indexed"] = 1
            stats["chunks"] = chunk_count
        return stats

    def _reset_all(self, stats: dict) -> None:
        rows = self.db.execute(text("SELECT id FROM documents")).mappings().all()
        for row in rows:
            self.chroma.delete_by_document_id(row["id"])
            stats["removed"] += 1

        self.db.execute(text("DELETE FROM document_chunks"))
        self.db.execute(text("DELETE FROM documents"))
        self.chroma.reset()

    def _list_document_paths(self) -> list[str]:
        rows = self.db.execute(text("SELECT source_path FROM documents")).all()
        return [row[0] for row in rows]

    def _get_document_by_path(self, source_path: str) -> dict[str, Any] | None:
        row = self.db.execute(
            text(
                """
                SELECT
                    id,
                    source_path,
                    title,
                    content_hash,
                    updated_at,
                    file_mtime,
                    chunk_count,
                    index_status,
                    indexed_at,
                    embedding_model,
                    embedding_dimension
                FROM documents
                WHERE source_path = :source_path
                """
            ),
            {"source_path": source_path},
        ).mappings().first()
        return dict(row) if row is not None else None

    def _remove_document_by_path(self, source_path: str) -> None:
        document = self._get_document_by_path(source_path)
        if document is None:
            return
        self._delete_document_chunks(document["id"])
        self.db.execute(
            text("DELETE FROM documents WHERE id = :id"),
            {"id": document["id"]},
        )

    def _delete_document_chunks(self, document_id: int) -> None:
        """只删除该 document 自己的 chunk（SQL + Chroma），不影响其他文件。"""
        rows = self.db.execute(
            text(
                """
                SELECT chroma_id
                FROM document_chunks
                WHERE document_id = :document_id
                """
            ),
            {"document_id": document_id},
        ).all()
        chroma_ids = [row[0] for row in rows if row[0]]

        # 以 SQL 中记录的 chroma_id 为准删除，避免 where 过滤误伤其他文档
        if chroma_ids:
            self.chroma.delete_by_chroma_ids(chroma_ids)
        # 兜底清理该 document_id 的残留向量（内部会二次校验 metadata）
        self.chroma.delete_by_document_id(document_id)

        self.db.execute(
            text("DELETE FROM document_chunks WHERE document_id = :document_id"),
            {"document_id": document_id},
        )

    def _insert_document(self, parsed_doc: ParsedDocument) -> int:
        result = self.db.execute(
            text(
                """
                INSERT INTO documents (
                    source_path,
                    title,
                    content_hash,
                    updated_at,
                    file_mtime,
                    chunk_count,
                    index_status,
                    embedding_model,
                    embedding_dimension
                ) VALUES (
                    :source_path,
                    :title,
                    :content_hash,
                    :updated_at,
                    :file_mtime,
                    0,
                    'pending',
                    NULL,
                    NULL
                )
                """
            ),
            {
                "source_path": parsed_doc.source_path,
                "title": parsed_doc.title,
                "content_hash": parsed_doc.content_hash,
                "updated_at": parsed_doc.updated_at,
                "file_mtime": parsed_doc.file_mtime,
            },
        )
        return int(result.lastrowid)

    def _update_document_pending(self, document_id: int, parsed_doc: ParsedDocument) -> None:
        self.db.execute(
            text(
                """
                UPDATE documents
                SET
                    title = :title,
                    content_hash = :content_hash,
                    updated_at = :updated_at,
                    file_mtime = :file_mtime,
                    index_status = 'pending'
                WHERE id = :id
                """
            ),
            {
                "id": document_id,
                "title": parsed_doc.title,
                "content_hash": parsed_doc.content_hash,
                "updated_at": parsed_doc.updated_at,
                "file_mtime": parsed_doc.file_mtime,
            },
        )

    def _update_document_indexed(
        self,
        document_id: int,
        *,
        chunk_count: int,
        title: str,
        updated_at: str | None,
    ) -> None:
        self.db.execute(
            text(
                """
                UPDATE documents
                SET
                    title = :title,
                    updated_at = :updated_at,
                    chunk_count = :chunk_count,
                    index_status = 'indexed',
                    indexed_at = :indexed_at,
                    embedding_model = :embedding_model,
                    embedding_dimension = :embedding_dimension
                WHERE id = :id
                """
            ),
            {
                "id": document_id,
                "title": title,
                "updated_at": updated_at,
                "chunk_count": chunk_count,
                "indexed_at": datetime.now(UTC),
                "embedding_model": self.embedder.model_name,
                "embedding_dimension": self.embedder.dimension,
            },
        )

    def _insert_chunk(
        self,
        *,
        document_id: int,
        chunk_index: int,
        content: str,
        content_hash: str,
        char_start: int | None,
        char_end: int | None,
    ) -> int:
        result = self.db.execute(
            text(
                """
                INSERT INTO document_chunks (
                    document_id,
                    chunk_index,
                    content,
                    content_hash,
                    char_start,
                    char_end,
                    chroma_id
                ) VALUES (
                    :document_id,
                    :chunk_index,
                    :content,
                    :content_hash,
                    :char_start,
                    :char_end,
                    :chroma_id
                )
                """
            ),
            {
                "document_id": document_id,
                "chunk_index": chunk_index,
                "content": content,
                "content_hash": content_hash,
                "char_start": char_start,
                "char_end": char_end,
                "chroma_id": "",
            },
        )
        return int(result.lastrowid)

    def _update_chunk_chroma_id(self, chunk_id: int, chroma_id: str) -> None:
        self.db.execute(
            text(
                """
                UPDATE document_chunks
                SET chroma_id = :chroma_id
                WHERE id = :id
                """
            ),
            {"id": chunk_id, "chroma_id": chroma_id},
        )

    def _index_document(self, parsed_doc: ParsedDocument, force: bool = False) -> int:
        """
        单文档增量规则：
        - 同文件且 content_hash 相同且已 indexed → 跳过
        - 同文件内容有差异（或 force）→ 仅删除该文件的 document_chunks + 对应 chroma，再重建
        - 新文件 → 只新增，不触碰其他文件
        """
        existing = self._get_document_by_path(parsed_doc.source_path)
        if (
            not force
            and existing is not None
            and existing["content_hash"] == parsed_doc.content_hash
            and existing["index_status"] == "indexed"
        ):
            return 0

        if existing is None:
            document_id = self._insert_document(parsed_doc)
            title = parsed_doc.title
            updated_at = parsed_doc.updated_at
        else:
            document_id = int(existing["id"])
            self._update_document_pending(document_id, parsed_doc)
            title = parsed_doc.title
            updated_at = parsed_doc.updated_at
            # 仅当已有同文件记录且需要重写时，删除该文件自己的旧 chunk
            self._delete_document_chunks(document_id)

        text_chunks = split_document(parsed_doc)
        if not text_chunks:
            self._update_document_indexed(
                document_id,
                chunk_count=0,
                title=title,
                updated_at=updated_at,
            )
            return 0

        db_chunks: list[dict[str, Any]] = []
        for text_chunk in text_chunks:
            chunk_id = self._insert_chunk(
                document_id=document_id,
                chunk_index=text_chunk.chunk_index,
                content=text_chunk.content,
                content_hash=text_chunk.content_hash,
                char_start=text_chunk.char_start,
                char_end=text_chunk.char_end,
            )
            chroma_id = f"chunk:{chunk_id}"
            self._update_chunk_chroma_id(chunk_id, chroma_id)
            db_chunks.append(
                {
                    "id": chunk_id,
                    "chunk_index": text_chunk.chunk_index,
                    "content": text_chunk.content,
                    "chroma_id": chroma_id,
                }
            )

        embeddings = self.embedder.embed_documents([chunk["content"] for chunk in db_chunks])
        metadatas = [
            {
                "document_id": document_id,
                "chunk_id": chunk["id"],
                "chunk_index": chunk["chunk_index"],
                "source_path": parsed_doc.source_path,
                "title": title,
                "updated_at": updated_at or "",
            }
            for chunk in db_chunks
        ]

        self.chroma.upsert(
            chroma_ids=[chunk["chroma_id"] for chunk in db_chunks],
            documents=[chunk["content"] for chunk in db_chunks],
            embeddings=embeddings,
            metadatas=metadatas,
        )

        self._update_document_indexed(
            document_id,
            chunk_count=len(db_chunks),
            title=title,
            updated_at=updated_at,
        )
        return len(db_chunks)
