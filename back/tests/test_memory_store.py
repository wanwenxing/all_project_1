"""memory_store 单元测试（SQLite profile + Chroma general）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.conversation.memory_chroma import clear_memory_chroma_cache, get_memory_chroma_store
from app.conversation.memory_store import (
    load_identity_profile,
    load_recent_general_hints,
    parse_memory_json,
    save_memory_split,
    search_general_memories,
)
from app.core.config import settings
from app.db.base import Base
from app.models import chat_session, user, user_memory_profile  # noqa: F401


class _FakeEmbedder:
    dimension = 8

    def embed_query(self, text: str) -> list[float]:
        seed = sum(ord(c) for c in text) % 97
        return [0.01 * ((seed + i) % 11) for i in range(self.dimension)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]


@pytest.fixture
def memory_db(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "rag_chroma_dir", str(tmp_path / "chroma"))
    clear_memory_chroma_cache()
    monkeypatch.setattr(
        "app.conversation.memory_store.get_embedder",
        lambda: _FakeEmbedder(),
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        clear_memory_chroma_cache()


def test_parse_memory_json_from_codeblock():
    raw = '说明\n```json\n{"profile": ["用户是大学生"], "general": ["喜欢 Python"]}\n```'
    parsed = parse_memory_json(raw)
    assert parsed["profile"] == ["用户是大学生"]
    assert parsed["general"] == ["喜欢 Python"]


def test_profile_overwrite_and_general_append(memory_db):
    first = save_memory_split(
        "1",
        profile=["用户是大学生"],
        general=["偏好 Python"],
        db=memory_db,
    )
    second = save_memory_split(
        "1",
        profile=["用户是大学生", "用户姓名是小明"],
        general=["偏好 TypeScript"],
        db=memory_db,
    )

    assert first["profile"] == ["用户是大学生"]
    assert second["profile"] == ["用户是大学生", "用户姓名是小明"]
    assert load_identity_profile("1", db=memory_db) == ["用户是大学生", "用户姓名是小明"]

    chroma = get_memory_chroma_store()
    assert chroma.count() == 2

    lines = search_general_memories("1", "TypeScript 编程偏好")
    assert "偏好 TypeScript" in lines


def test_search_general_memories_scoped_by_user(memory_db):
    save_memory_split(
        "1",
        profile=["用户是大学生"],
        general=["讨论过求职准备"],
        db=memory_db,
    )
    save_memory_split(
        "2",
        profile=[],
        general=["喜欢旅游"],
        db=memory_db,
    )

    assert search_general_memories("1", "求职") == ["讨论过求职准备"]
    assert search_general_memories("2", "旅游") == ["喜欢旅游"]


def test_load_recent_general_hints(memory_db):
    save_memory_split("1", profile=[], general=["记忆 A"], db=memory_db)
    save_memory_split("1", profile=[], general=["记忆 B"], db=memory_db)
    hints = load_recent_general_hints("1", limit=5)
    assert set(hints) == {"记忆 A", "记忆 B"}
