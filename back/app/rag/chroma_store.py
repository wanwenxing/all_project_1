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
        """仅删除指定 document_id 的向量；过滤结果会再校验 metadata，避免误删全库。"""
        target = str(document_id)
        # 兼容历史 int / 当前 str 两种 metadata
        candidates: list[str] = []
        for where in (
            {"document_id": {"$eq": target}},
            {"document_id": {"$eq": int(document_id)}},
        ):
            try:
                existing = self._collection.get(where=where, include=["metadatas"])
            except Exception:
                continue
            ids = existing.get("ids") or []
            metadatas = existing.get("metadatas") or []
            for index, chroma_id in enumerate(ids):
                meta = metadatas[index] if index < len(metadatas) else None
                if meta is None:
                    continue
                if str(meta.get("document_id")) == target:
                    candidates.append(chroma_id)

        # 去重后删除；没有任何命中则绝不调用 delete
        unique_ids = list(dict.fromkeys(candidates))
        if unique_ids:
            self._collection.delete(ids=unique_ids)

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
        # Chroma metadata 统一用可序列化基础类型；document_id 用字符串便于精确过滤
        normalized = []
        for meta in metadatas:
            item = dict(meta)
            if "document_id" in item:
                item["document_id"] = str(item["document_id"])
            if "chunk_id" in item:
                item["chunk_id"] = str(item["chunk_id"])
            if "chunk_index" in item:
                item["chunk_index"] = int(item["chunk_index"])
            normalized.append(item)

        self._collection.upsert(
            ids=chroma_ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=normalized,
        )

    def count(self) -> int:
        return self._collection.count()

    def query(
        self,
        query_embedding: list[float],
        *,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """向量检索；可选 metadata where 过滤。返回按相似度排序的命中列表。"""
        total = self._collection.count()
        if total == 0:
            return []

        top_k = max(1, min(n_results, total))
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        result = self._collection.query(**kwargs)
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        hits: list[dict] = []
        for index, chroma_id in enumerate(ids):
            distance = float(distances[index]) if index < len(distances) else None
            meta = metadatas[index] if index < len(metadatas) else {}
            hits.append(
                {
                    "chroma_id": chroma_id,
                    "content": documents[index] if index < len(documents) else "",
                    "distance": distance,
                    # cosine distance：越小越相似；score 近似相似度
                    "score": None if distance is None else max(0.0, 1.0 - distance),
                    "metadata": meta or {},
                }
            )
        return hits


def get_chroma_store() -> ChromaStore:
    return ChromaStore()
