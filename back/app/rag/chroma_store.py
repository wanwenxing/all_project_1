from pathlib import Path

import chromadb

from app.core.config import settings


class ChromaStore:
    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        self.persist_dir = Path(persist_dir or settings.rag_chroma_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name or settings.rag_collection_name
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_by_document_id(self, document_id: int) -> None:
        existing = self._collection.get(where={"document_id": document_id})
        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])

    def delete_by_chroma_ids(self, chroma_ids: list[str]) -> None:
        if chroma_ids:
            self._collection.delete(ids=chroma_ids)

    def upsert(
        self,
        chroma_ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        if not chroma_ids:
            return
        self._collection.upsert(
            ids=chroma_ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def count(self) -> int:
        return self._collection.count()


def get_chroma_store() -> ChromaStore:
    return ChromaStore()
