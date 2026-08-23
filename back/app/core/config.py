from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACK_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACK_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "back"
    debug: bool = True

    host: str = "0.0.0.0"
    port: int = 3000

    database_url: str = "sqlite:///./data/app.db"

    secret_key: str = "change-me-to-a-random-secret-key"
    access_token_expire_minutes: int = 60

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    rag_docs_dir: str = "./docs"
    rag_chroma_dir: str = "./data/chroma"
    rag_model_cache_dir: str = "./data/models"
    rag_collection_name: str = "diary_chunks"
    rag_embedding_model: str = "BAAI/bge-large-zh-v1.5"
    rag_chunk_size: int = 300
    rag_chunk_overlap: int = 50
    # 向量召回最低相关度（仅在未启用 rerank 时作为粗过滤）
    rag_min_score: float = 0.5
    # 混合检索 + Rerank
    rag_hybrid_enabled: bool = True
    rag_fetch_k: int = 5
    rag_candidate_k: int = 5
    rag_rrf_k: int = 60
    rag_rerank_enabled: bool = True
    rag_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rag_default_top_k: int = 2

    # DeepSeek / OpenAI-compatible chat API
    llm_api_key: str = "sk-e5241ee66f054923a20baa4dafd79e44"
    llm_base_url: str = "https://ai.shebao.net/gatewa"
    llm_model: str = "zh-dev-deepseek-v4-flash"
    llm_timeout_seconds: float = 60.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
