"""memory_store 单元测试（不依赖 LLM / embedding）。"""

from __future__ import annotations

from langgraph.store.memory import InMemoryStore

from app.conversation.memory_store import (
    PROFILE_KEY,
    load_identity_profile,
    parse_memory_json,
    save_memory_split,
    search_general_memories,
)


def test_parse_memory_json_from_codeblock():
    raw = '说明\n```json\n{"profile": ["用户是大学生"], "general": ["喜欢 Python"]}\n```'
    parsed = parse_memory_json(raw)
    assert parsed["profile"] == ["用户是大学生"]
    assert parsed["general"] == ["喜欢 Python"]


def test_profile_overwrite_and_general_append():
    store = InMemoryStore()
    namespace = ("memories", "u1")

    first = save_memory_split(
        store,
        namespace,
        profile=["用户是大学生"],
        general=["偏好 Python"],
    )
    second = save_memory_split(
        store,
        namespace,
        profile=["用户是大学生", "用户姓名是小明"],
        general=["偏好 TypeScript"],
    )

    assert first["profile"] == ["用户是大学生"]
    assert second["profile"] == ["用户是大学生", "用户姓名是小明"]
    assert load_identity_profile(store, namespace) == ["用户是大学生", "用户姓名是小明"]

    item = store.get(namespace, PROFILE_KEY)
    assert item is not None
    assert item.value == {"identity": ["用户是大学生", "用户姓名是小明"]}

    general_hits = store.search(namespace, filter={"category": "general"}, limit=10)
    assert len(general_hits) == 2
    texts = {str(hit.value.get("data")) for hit in general_hits}
    assert texts == {"偏好 Python", "偏好 TypeScript"}


def test_search_general_memories_excludes_profile():
    store = InMemoryStore()
    namespace = ("memories", "u2")
    save_memory_split(
        store,
        namespace,
        profile=["用户是大学生"],
        general=["讨论过求职准备"],
    )
    lines = search_general_memories(store, namespace, "求职")
    assert lines == ["讨论过求职准备"]
