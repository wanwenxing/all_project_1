"""长期 general 记忆：独立 Chroma collection + BGE 向量检索。"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.rag.chroma_store import ChromaStore


@lru_cache(maxsize=1)
def get_memory_chroma_store() -> ChromaStore:
    return ChromaStore(collection_name=settings.memory_chroma_collection)


def clear_memory_chroma_cache() -> None:
    get_memory_chroma_store.cache_clear()
