from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
BGE_PASSAGE_PREFIX = ""


def _model_cache_dir() -> Path:
    path = Path(settings.rag_model_cache_dir)
    if not path.is_absolute():
        path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _project_snapshot_dir(model_name: str) -> Path:
    safe_name = model_name.replace("/", "--")
    return _model_cache_dir() / safe_name


def _hf_hub_snapshot_dir(model_name: str) -> Path | None:
    """复用本机已下载的 Hugging Face hub 缓存，避免再次联网。"""
    hub_root = Path.home() / ".cache" / "huggingface" / "hub"
    repo_dir = hub_root / f"models--{model_name.replace('/', '--')}"
    ref_file = repo_dir / "refs" / "main"
    if not ref_file.is_file():
        return None
    revision = ref_file.read_text(encoding="utf-8").strip()
    snapshot = repo_dir / "snapshots" / revision
    if (snapshot / "config.json").is_file():
        return snapshot
    return None


def _is_ready_model_dir(path: Path) -> bool:
    return (path / "config.json").is_file()


def _ensure_local_model(model_name: str) -> str:
    """
    解析本地模型路径，优先级：
    1. 项目 data/models
    2. 用户目录 Hugging Face hub 缓存
    3. 仅在前两者都没有时才联网下载到 data/models
    """
    project_dir = _project_snapshot_dir(model_name)
    if _is_ready_model_dir(project_dir):
        return str(project_dir)

    hub_dir = _hf_hub_snapshot_dir(model_name)
    if hub_dir is not None:
        return str(hub_dir)

    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=model_name,
        local_dir=str(project_dir),
        local_dir_use_symlinks=False,
        local_files_only=False,
    )
    return str(project_dir)


class BGEEmbedder:
    model_name: str = settings.rag_embedding_model
    dimension: int = 1024

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.rag_embedding_model
        self._model: SentenceTransformer | None = None
        self._resolved_path: str | None = None

    @property
    def model(self) -> "SentenceTransformer":
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._resolved_path = _ensure_local_model(self.model_name)
            self._model = SentenceTransformer(
                self._resolved_path,
                local_files_only=True,
            )
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
