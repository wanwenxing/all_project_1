"""记忆对话：会话元数据（SQLite）+ LangGraph checkpoint + 长期记忆。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.conversation.memory_backends import get_checkpointer
from app.conversation.memory_chroma import clear_memory_chroma_cache
from app.conversation.memory_graph import (
    build_memory_chat_graph_with_backends,
    extract_thread_messages,
)
from app.core.ask_cancel import AskCancelled, AskCancelToken
from app.core.ask_errors import (
    AskFailure,
    build_done_event,
    build_error_event,
    classify_ask_exception,
)
from app.db.session import SessionLocal
from app.llm import get_llm_client
from app.models.chat_session import ChatSession
from app.models.user_memory_profile import UserMemoryProfile


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_user_id(user_id: str) -> int:
    return int(user_id)


def _session_to_dict(row: ChatSession) -> dict[str, Any]:
    return {
        "thread_id": row.thread_id,
        "title": row.title,
        "created_at": row.created_at,
    }


def _db_session() -> Session:
    return SessionLocal()


def reset_memory_chat_for_tests() -> None:
    clear_memory_chroma_cache()
    db = _db_session()
    try:
        db.query(UserMemoryProfile).delete()
        db.query(ChatSession).delete()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_session(user_id: str, title: str | None = None) -> dict[str, Any]:
    uid = _parse_user_id(user_id)
    thread_id = uuid.uuid4().hex
    db = _db_session()
    try:
        count = db.query(ChatSession).filter(ChatSession.user_id == uid).count()
        session = ChatSession(
            user_id=uid,
            thread_id=thread_id,
            title=(title or "").strip() or f"窗口 {count + 1}",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return _session_to_dict(session)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    uid = _parse_user_id(user_id)
    db = _db_session()
    try:
        rows = (
            db.query(ChatSession)
            .filter(ChatSession.user_id == uid)
            .order_by(ChatSession.created_at.desc())
            .all()
        )
        return [_session_to_dict(row) for row in rows]
    finally:
        db.close()


def delete_session(user_id: str, thread_id: str) -> bool:
    uid = _parse_user_id(user_id)
    db = _db_session()
    try:
        row = (
            db.query(ChatSession)
            .filter(ChatSession.user_id == uid, ChatSession.thread_id == thread_id)
            .first()
        )
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_session(user_id: str, thread_id: str) -> dict[str, Any]:
    uid = _parse_user_id(user_id)
    db = _db_session()
    try:
        row = (
            db.query(ChatSession)
            .filter(ChatSession.user_id == uid, ChatSession.thread_id == thread_id)
            .first()
        )
        if row is not None:
            return _session_to_dict(row)

        count = db.query(ChatSession).filter(ChatSession.user_id == uid).count()
        row = ChatSession(
            user_id=uid,
            thread_id=thread_id,
            title=f"窗口 {count + 1}",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _session_to_dict(row)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def get_session_messages(user_id: str, thread_id: str) -> list[dict[str, str]]:
    ensure_session(user_id, thread_id)
    llm = get_llm_client()
    llm.ensure_configured()
    checkpointer = get_checkpointer()
    graph = build_memory_chat_graph_with_backends(llm, checkpointer=checkpointer)
    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,
        }
    }
    state = await graph.aget_state(config)
    values = state.values if state else {}
    return extract_thread_messages(values.get("messages") or [])


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

    checkpointer = get_checkpointer()
    graph = build_memory_chat_graph_with_backends(
        llm,
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
