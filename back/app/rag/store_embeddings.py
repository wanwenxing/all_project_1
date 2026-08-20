"""把知识库 BGEEmbedder 适配成 LangChain Embeddings，供 LangGraph Store 使用。"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.embeddings import Embeddings

from app.rag.embedder import BGEEmbedder, get_embedder


class BGEStoreEmbeddings(Embeddings):
    """InMemoryStore(index={'embed': ...}) 所需接口。"""

    def __init__(self, embedder: BGEEmbedder | None = None) -> None:
        self._embedder = embedder or get_embedder()
        self.dims = self._embedder.dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.embed_query(text)


@lru_cache(maxsize=1)
def get_store_embeddings() -> BGEStoreEmbeddings:
    return BGEStoreEmbeddings()
