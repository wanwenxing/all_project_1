from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
BGE_PASSAGE_PREFIX = ""


class BGEEmbedder:
    model_name: str = settings.rag_embedding_model
    dimension: int = 1024

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.rag_embedding_model
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> "SentenceTransformer":
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        prefixed = [f"{BGE_PASSAGE_PREFIX}{text}" for text in texts]
        vectors = self.model.encode(prefixed, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self.model.encode(
            f"{BGE_QUERY_PREFIX}{text}",
            normalize_embeddings=True,
        )
        return vector.tolist()


@lru_cache(maxsize=1)
def get_embedder() -> BGEEmbedder:
    return BGEEmbedder()
