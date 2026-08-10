from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.rag.embedder import _ensure_local_model


class BGEReranker:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.rag_reranker_model
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            resolved = _ensure_local_model(self.model_name)
            self._model = CrossEncoder(resolved)
        return self._model

    def rerank(
        self,
        query: str,
        hits: list[dict[str, Any]],
        *,
        top_k: int,
    ) -> list[dict[str, Any]]:
        if not hits:
            return []
        if top_k <= 0:
            return []

        pairs = [[query, hit.get("content") or ""] for hit in hits]
        raw_scores = self.model.predict(pairs)
        scored: list[tuple[float, dict[str, Any]]] = []
        for hit, raw in zip(hits, raw_scores, strict=False):
            score = float(raw)
            item = dict(hit)
            item["rerank_score"] = score
            item["score"] = score
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:top_k]]


@lru_cache(maxsize=1)
def get_reranker() -> BGEReranker:
    return BGEReranker()
