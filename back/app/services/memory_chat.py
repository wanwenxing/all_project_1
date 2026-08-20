"""记忆对话：会话元数据（进程内）+ LangGraph SSE。"""

from __future__ import annotations

import threading
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from app.core.ask_cancel import AskCancelled, AskCancelToken
from app.core.ask_errors import (
    AskFailure,
    build_done_event,
    build_error_event,
    classify_ask_exception,
)
from app.llm import get_llm_client
from app.rag.memory_graph import (
    build_memory_chat_graph_with_backends,
    create_shared_memory_backends,
)

_lock = threading.Lock()
_shared_store = None
_shared_checkpointer = None
# user_id -> list[session dict]
_sessions: dict[str, list[dict[str, Any]]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_backends():
    global _shared_store, _shared_checkpointer
    with _lock:
        if _shared_store is None or _shared_checkpointer is None:
            _shared_store, _shared_checkpointer = create_shared_memory_backends()
        return _shared_store, _shared_checkpointer


def reset_memory_chat_for_tests() -> None:
    global _shared_store, _shared_checkpointer, _sessions
    with _lock:
        _shared_store = None
        _shared_checkpointer = None
        _sessions = {}


def create_session(user_id: str, title: str | None = None) -> dict[str, Any]:
    thread_id = uuid.uuid4().hex
    with _lock:
        n = len(_sessions.get(user_id, [])) + 1
    session = {
        "thread_id": thread_id,
        "title": (title or "").strip() or f"窗口 {n}",
        "created_at": _utcnow(),
    }
    with _lock:
        _sessions.setdefault(user_id, []).append(session)
    return session


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    with _lock:
        return list(_sessions.get(user_id, []))


def delete_session(user_id: str, thread_id: str) -> bool:
    with _lock:
        items = _sessions.get(user_id, [])
        kept = [s for s in items if s["thread_id"] != thread_id]
        if len(kept) == len(items):
            return False
        _sessions[user_id] = kept
        return True


def ensure_session(user_id: str, thread_id: str) -> dict[str, Any]:
    with _lock:
        for session in _sessions.get(user_id, []):
            if session["thread_id"] == thread_id:
                return session
        n = len(_sessions.get(user_id, [])) + 1
    session = {
        "thread_id": thread_id,
        "title": f"窗口 {n}",
        "created_at": _utcnow(),
    }
    with _lock:
        _sessions.setdefault(user_id, []).append(session)
    return session


async def memory_chat_stream(
    *,
    user_id: str,
    thread_id: str,
    message: str,
    cancel: AskCancelToken | None = None,
) -> AsyncIterator[dict[str, Any]]:
    text = (message or "").strip()
    if not text:
        failure = AskFailure(kind="error", code="empty_message", message="消息不能为空")
        yield build_error_event("input", failure)
        yield build_done_event(failure, ok=False)
        return

    ensure_session(user_id, thread_id)
    llm = get_llm_client()
    try:
        llm.ensure_configured()
    except Exception as exc:  # noqa: BLE001
        failure = classify_ask_exception(exc, cancel=cancel)
        yield build_error_event("llm", failure)
        yield build_done_event(failure, ok=False)
        return

    store, checkpointer = _ensure_backends()
    graph = build_memory_chat_graph_with_backends(
        llm,
        store=store,
        checkpointer=checkpointer,
        cancel=cancel,
    )
    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,
        }
    }

    try:
        async for mode, payload in graph.astream(
            {"messages": [{"role": "user", "content": text}]},
            config,
            stream_mode=["custom", "values"],
        ):
            if cancel is not None and cancel.is_cancelled:
                raise AskCancelled()
            if mode == "custom" and isinstance(payload, dict):
                yield payload
        yield build_done_event(ok=True)
    except AskCancelled:
        failure = AskFailure(kind="cancelled", code="cancelled", message="已取消")
        yield build_error_event("cancelled", failure)
        yield build_done_event(failure, ok=False)
    except Exception as exc:  # noqa: BLE001
        failure = classify_ask_exception(exc, cancel=cancel)
        yield build_error_event("chat", failure)
        yield build_done_event(failure, ok=False)
