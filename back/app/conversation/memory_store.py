"""长期记忆读写：profile 固定 key 全量更新，general 逐条追加。"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from langgraph.store.base import BaseStore

PROFILE_KEY = "profile"
GENERAL_CATEGORY = "general"
RECENT_GENERAL_HINT_LIMIT = 5
GENERAL_SEARCH_LIMIT = 5


def load_identity_profile(store: BaseStore, namespace: tuple[str, ...]) -> list[str]:
    item = store.get(namespace, PROFILE_KEY)
    if not item or not item.value:
        return []
    raw = item.value.get("identity") or []
    if not isinstance(raw, list):
        return []
    return [str(line).strip() for line in raw if str(line).strip()]


def load_recent_general_hints(
    store: BaseStore,
    namespace: tuple[str, ...],
    *,
    limit: int = RECENT_GENERAL_HINT_LIMIT,
) -> list[str]:
    hits = store.search(
        namespace,
        filter={"category": GENERAL_CATEGORY},
        limit=limit,
    )
    lines: list[str] = []
    for item in hits:
        if not item.value:
            continue
        text = str(item.value.get("data") or "").strip()
        if text:
            lines.append(text)
    return lines


def search_general_memories(
    store: BaseStore,
    namespace: tuple[str, ...],
    query: str,
    *,
    limit: int = GENERAL_SEARCH_LIMIT,
) -> list[str]:
    hits = store.search(
        namespace,
        query=query,
        filter={"category": GENERAL_CATEGORY},
        limit=limit,
    )
    lines: list[str] = []
    for item in hits:
        if not item.value:
            continue
        text = str(item.value.get("data") or "").strip()
        if text:
            lines.append(text)
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
    store: BaseStore,
    namespace: tuple[str, ...],
    *,
    profile: list[str],
    general: list[str],
) -> dict[str, Any]:
    """profile 覆盖固定 key；general 每条追加新 uuid。"""
    saved_profile: list[str] = []
    saved_general: list[str] = []

    if profile:
        store.put(
            namespace,
            PROFILE_KEY,
            {"identity": profile},
            index=False,
        )
        saved_profile = list(profile)

    for text in general:
        line = text.strip()
        if not line:
            continue
        store.put(
            namespace,
            str(uuid.uuid4()),
            {"category": GENERAL_CATEGORY, "data": line},
        )
        saved_general.append(line)

    return {"profile": saved_profile, "general": saved_general}


def _normalize_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
