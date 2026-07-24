from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
