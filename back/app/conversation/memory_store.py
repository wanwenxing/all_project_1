"""长期记忆读写：profile 存 SQLite，general 存 Chroma 向量库。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.conversation.memory_chroma import get_memory_chroma_store
from app.db.session import SessionLocal
from app.models.user_memory_profile import UserMemoryProfile
from app.rag.embedder import get_embedder

GENERAL_CATEGORY = "general"
RECENT_GENERAL_HINT_LIMIT = 5
GENERAL_SEARCH_LIMIT = 5


def _parse_user_id(user_id: str) -> int:
    return int(user_id)


def _identity_from_json(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def load_identity_profile(user_id: str, *, db: Session | None = None) -> list[str]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        row = session.get(UserMemoryProfile, _parse_user_id(user_id))
        if row is None:
            return []
        return _identity_from_json(row.identity_json)
    finally:
        if owns_session:
            session.close()


def load_recent_general_hints(
    user_id: str,
    *,
    limit: int = RECENT_GENERAL_HINT_LIMIT,
) -> list[str]:
    """读取该用户最近写入的 general，供总结时避免重复输出。"""
    chroma = get_memory_chroma_store()
    result = chroma._collection.get(
        where={"user_id": str(user_id)},
        include=["documents", "metadatas"],
    )
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []

    rows: list[tuple[str, str]] = []
    for index, doc in enumerate(documents):
        text = str(doc or "").strip()
        if not text:
            continue
        meta = metadatas[index] if index < len(metadatas) else {}
        created_at = str((meta or {}).get("created_at") or "")
        rows.append((created_at, text))

    rows.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in rows[:limit]]


def search_general_memories(
    user_id: str,
    query: str,
    *,
    limit: int = GENERAL_SEARCH_LIMIT,
) -> list[str]:
    text = (query or "").strip()
    if not text:
        return []

    embedder = get_embedder()
    query_embedding = embedder.embed_query(text)
    hits = get_memory_chroma_store().query(
        query_embedding,
        n_results=limit,
        where={"user_id": str(user_id)},
    )
    lines: list[str] = []
    for hit in hits:
        content = str(hit.get("content") or "").strip()
        if content:
            lines.append(content)
    return lines


def parse_memory_json(raw: str) -> dict[str, list[str]]:
    text = (raw or "").strip()
    if not text:
        return {"profile": [], "general": []}

    candidates = [text]
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        candidates.insert(0, fence.group(1).strip())
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        candidates.append(brace.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        return {
            "profile": _normalize_lines(parsed.get("profile")),
            "general": _normalize_lines(parsed.get("general")),
        }

    return {"profile": [], "general": []}


def save_memory_split(
    user_id: str,
    *,
    profile: list[str],
    general: list[str],
    db: Session | None = None,
) -> dict[str, Any]:
    """profile 覆盖 SQLite 一行；general 每条追加到 Chroma。"""
    saved_profile: list[str] = []
    saved_general: list[str] = []

    owns_session = db is None
    session = db or SessionLocal()
    try:
        if profile:
            uid = _parse_user_id(user_id)
            row = session.get(UserMemoryProfile, uid)
            identity_json = json.dumps(profile, ensure_ascii=False)
            if row is None:
                session.add(UserMemoryProfile(user_id=uid, identity_json=identity_json))
            else:
                row.identity_json = identity_json
            session.commit()
            saved_profile = list(profile)

        if general:
            embedder = get_embedder()
            chroma = get_memory_chroma_store()
            for text in general:
                line = text.strip()
                if not line:
                    continue
                embedding = embedder.embed_query(line)
                chroma.upsert(
                    chroma_ids=[str(uuid.uuid4())],
                    documents=[line],
                    embeddings=[embedding],
                    metadatas=[
                        {
                            "user_id": str(user_id),
                            "category": GENERAL_CATEGORY,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ],
                )
                saved_general.append(line)
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()

    return {"profile": saved_profile, "general": saved_general}


def _normalize_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
