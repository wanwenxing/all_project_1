from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.rag.chroma_store import ChromaStore, get_chroma_store
from app.rag.embedder import BGEEmbedder, get_embedder
from app.rag.loader import load_documents
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

    def _reset_all(self, stats: dict) -> None:
        for document in self.db.scalars(select(Document)).all():
            self.chroma.delete_by_document_id(document.id)
            stats["removed"] += 1
        self.db.query(DocumentChunk).delete()
        self.db.query(Document).delete()
        self.chroma.reset()
        self.db.flush()

    def _list_document_paths(self) -> list[str]:
        return list(self.db.scalars(select(Document.source_path)).all())

    def _get_document_by_path(self, source_path: str) -> Document | None:
        return self.db.scalar(select(Document).where(Document.source_path == source_path))

    def _remove_document_by_path(self, source_path: str) -> None:
        document = self._get_document_by_path(source_path)
        if document is None:
            return
        self._delete_document_chunks(document)
        self.db.delete(document)
        self.db.flush()

    def _delete_document_chunks(self, document: Document) -> None:
        chroma_ids = [chunk.chroma_id for chunk in document.chunks]
        self.chroma.delete_by_chroma_ids(chroma_ids)
        self.chroma.delete_by_document_id(document.id)
        for chunk in list(document.chunks):
            self.db.delete(chunk)
        self.db.flush()

    def _index_document(self, parsed_doc: ParsedDocument, force: bool = False) -> int:
        existing = self._get_document_by_path(parsed_doc.source_path)
        if (
            not force
            and existing is not None
            and existing.content_hash == parsed_doc.content_hash
            and existing.index_status == "indexed"
        ):
            return 0

        document = existing or Document(
            source_path=parsed_doc.source_path,
            title=parsed_doc.title,
            content_hash=parsed_doc.content_hash,
        )
        document.title = parsed_doc.title
        document.content_hash = parsed_doc.content_hash
        document.updated_at = parsed_doc.updated_at
        document.file_mtime = parsed_doc.file_mtime
        document.index_status = "pending"

        if existing is None:
            self.db.add(document)
        self.db.flush()

        self._delete_document_chunks(document)

        text_chunks = split_document(parsed_doc)
        if not text_chunks:
            document.chunk_count = 0
            document.index_status = "indexed"
            document.indexed_at = datetime.now(UTC)
            document.embedding_model = self.embedder.model_name
            document.embedding_dimension = self.embedder.dimension
            self.db.flush()
            return 0

        db_chunks: list[DocumentChunk] = []
        for text_chunk in text_chunks:
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=text_chunk.chunk_index,
                content=text_chunk.content,
                content_hash=text_chunk.content_hash,
                char_start=text_chunk.char_start,
                char_end=text_chunk.char_end,
                chroma_id="",
            )
            self.db.add(chunk)
            db_chunks.append(chunk)
        self.db.flush()

        for chunk in db_chunks:
            chunk.chroma_id = f"chunk:{chunk.id}"

        embeddings = self.embedder.embed_documents([chunk.content for chunk in db_chunks])
        metadatas = [
            {
                "document_id": document.id,
                "chunk_id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "source_path": document.source_path,
                "title": document.title,
                "updated_at": document.updated_at or "",
            }
            for chunk in db_chunks
        ]

        self.chroma.upsert(
            chroma_ids=[chunk.chroma_id for chunk in db_chunks],
            documents=[chunk.content for chunk in db_chunks],
            embeddings=embeddings,
            metadatas=metadatas,
        )

        document.chunk_count = len(db_chunks)
        document.index_status = "indexed"
        document.indexed_at = datetime.now(UTC)
        document.embedding_model = self.embedder.model_name
        document.embedding_dimension = self.embedder.dimension
        self.db.flush()
        return len(db_chunks)
