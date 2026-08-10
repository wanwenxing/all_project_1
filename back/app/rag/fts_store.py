from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.rag.tokenize import build_fts_query, tokenize_for_fts

CREATE_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    content,
    tokenize = 'unicode61'
)
"""


class FTSStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_schema(self) -> None:
        self.db.execute(text(CREATE_FTS_SQL))

    def clear(self) -> None:
        self.ensure_schema()
        # FTS5 清空：删除全部行
        self.db.execute(text("DELETE FROM chunk_fts"))

    def delete_by_document_id(self, document_id: int) -> None:
        self.ensure_schema()
        self.db.execute(
            text("DELETE FROM chunk_fts WHERE document_id = :document_id"),
            {"document_id": document_id},
        )

    def delete_by_chunk_id(self, chunk_id: int) -> None:
        self.ensure_schema()
        self.db.execute(
            text("DELETE FROM chunk_fts WHERE chunk_id = :chunk_id"),
            {"chunk_id": chunk_id},
        )

    def upsert_chunk(self, *, chunk_id: int, document_id: int, content: str) -> None:
        self.ensure_schema()
        self.delete_by_chunk_id(chunk_id)
        tokenized = tokenize_for_fts(content)
        if not tokenized:
            return
        self.db.execute(
            text(
                """
                INSERT INTO chunk_fts (chunk_id, document_id, content)
                VALUES (:chunk_id, :document_id, :content)
                """
            ),
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "content": tokenized,
            },
        )

    def backfill_from_chunks(self) -> int:
        """从 document_chunks 全量重建 FTS（迁移/修复用）。"""
        self.ensure_schema()
        self.clear()
        rows = self.db.execute(
            text(
                """
                SELECT id, document_id, content
                FROM document_chunks
                ORDER BY id
                """
            )
        ).mappings().all()
        count = 0
        for row in rows:
            self.upsert_chunk(
                chunk_id=int(row["id"]),
                document_id=int(row["document_id"]),
                content=row["content"] or "",
            )
            count += 1
        return count

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        source_path: str | None = None,
        title: str | None = None,
        updated_at: str | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        fts_query = build_fts_query(query)
        if not fts_query or limit <= 0:
            return []

        sql = """
            SELECT
                chunk_fts.chunk_id AS chunk_id,
                c.content AS content,
                c.chroma_id AS chroma_id,
                c.chunk_index AS chunk_index,
                c.document_id AS document_id,
                d.source_path AS source_path,
                d.title AS title,
                d.updated_at AS updated_at,
                bm25(chunk_fts) AS bm25_score
            FROM chunk_fts
            JOIN document_chunks AS c ON c.id = chunk_fts.chunk_id
            JOIN documents AS d ON d.id = c.document_id
            WHERE chunk_fts MATCH :fts_query
        """
        params: dict[str, Any] = {"fts_query": fts_query, "limit": limit}

        if source_path and source_path.strip():
            sql += " AND d.source_path = :source_path"
            params["source_path"] = source_path.strip().replace("\\", "/")
        if title and title.strip():
            sql += " AND d.title = :title"
            params["title"] = title.strip()
        if updated_at and updated_at.strip():
            sql += " AND d.updated_at = :updated_at"
            params["updated_at"] = updated_at.strip()

        # SQLite FTS5 bm25：通常越小（更负）越相关
        sql += " ORDER BY bm25_score LIMIT :limit"

        try:
            rows = self.db.execute(text(sql), params).mappings().all()
        except Exception:
            # MATCH 语法异常或空索引时，关键字路降级为空
            return []

        hits: list[dict[str, Any]] = []
        for rank, row in enumerate(rows, start=1):
            hits.append(
                {
                    "chroma_id": row["chroma_id"] or f"chunk:{row['chunk_id']}",
                    "content": row["content"] or "",
                    "distance": None,
                    "score": None,
                    "document_id": str(row["document_id"]),
                    "chunk_id": str(row["chunk_id"]),
                    "chunk_index": int(row["chunk_index"]) if row["chunk_index"] is not None else None,
                    "source_path": row["source_path"],
                    "title": row["title"],
                    "updated_at": row["updated_at"] or None,
                    "keyword_rank": rank,
                    "bm25_score": float(row["bm25_score"]) if row["bm25_score"] is not None else None,
                }
            )
        return hits
