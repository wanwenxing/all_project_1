import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (  # noqa: F401
    ask_log,
    chat_session,
    document,
    document_chunk,
    eval_models,
    user,
    user_memory_profile,
)
from app.conversation.memory_chroma import clear_memory_chroma_cache
from app.core.config import settings


@pytest.fixture
def client(monkeypatch, tmp_path):
    """使用独立内存库，避免测试 drop_all / 写库污染开发用的 data/app.db。"""
    monkeypatch.setattr(settings, "memory_checkpoint_path", str(tmp_path / "langgraph_checkpoints.db"))
    monkeypatch.setattr(settings, "rag_chroma_dir", str(tmp_path / "chroma"))
    clear_memory_chroma_cache()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # FastAPI 依赖与部分测试里直接 SessionLocal() 都切到内存库
    monkeypatch.setattr("app.db.session.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.services.ask.SessionLocal", TestingSessionLocal, raising=False)
    monkeypatch.setattr("app.services.memory_chat.SessionLocal", TestingSessionLocal, raising=False)
    monkeypatch.setattr("app.conversation.memory_store.SessionLocal", TestingSessionLocal, raising=False)
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
