from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.core.ask_cancel import AskCancelled, AskCancelToken
from app.core.ask_errors import (
    AskFailure,
    LLMNotConfiguredError,
    build_done_event,
    build_error_event,
    classify_ask_exception,
)
from app.llm import DeepSeekChatClient, get_llm_client
from app.models.ask_log import AskLog
from app.rag.ask_graph import AskState, build_ask_graph


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _persist_ask_log(
    db: Session | None,
    *,
    user_id: int | None,
    original_query: str,
    optimized_query: str | None,
    rewrite_fallback: bool,
    hits: list[dict[str, Any]],
    answer: str | None,
    status: str,
    error_stage: str | None,
    error_message: str | None,
    duration_ms: int | None,
    model: str | None,
) -> None:
    if db is None:
        return
    try:
        row = AskLog(
            user_id=user_id,
            status=status,
            error_stage=error_stage,
            error_message=error_message,
            original_query=original_query,
            optimized_query=optimized_query,
            rewrite_fallback=rewrite_fallback,
            retrieve_total=len(hits),
            retrieve_hits_json=json.dumps(hits, ensure_ascii=False) if hits else None,
            answer=answer,
            model=model,
            duration_ms=duration_ms,
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        # 日志失败不影响主流程
        return


async def ask_knowledge_base_stream(
    *,
    query: str,
    top_k: int = 2,
    source_path: str | None = None,
    title: str | None = None,
    updated_at: str | None = None,
    user_id: int | None = None,
    db: Session | None = None,
    llm: DeepSeekChatClient | None = None,
    cancel: AskCancelToken | None = None,
) -> AsyncIterator[str]:
    """跑 LangGraph 并 yield SSE；结束后写入 ask_logs。"""
    original = query.strip()
    client = llm or get_llm_client()
    started = time.perf_counter()

    try:
        client.ensure_configured()
    except LLMNotConfiguredError as exc:
        failure = classify_ask_exception(exc)
        yield _sse(build_error_event("config", failure))
        yield _sse(build_done_event(failure, ok=False))
        _persist_ask_log(
            db,
            user_id=user_id,
            original_query=original,
            optimized_query=None,
            rewrite_fallback=False,
            hits=[],
            answer=None,
            status=failure.log_status,
            error_stage="config",
            error_message=failure.message,
            duration_ms=int((time.perf_counter() - started) * 1000),
            model=client.model,
        )
        return

    if cancel is not None and cancel.is_cancelled:
        failure = classify_ask_exception(AskCancelled(), cancel=cancel)
        yield _sse(build_done_event(failure, ok=False))
        _persist_ask_log(
            db,
            user_id=user_id,
            original_query=original,
            optimized_query=None,
            rewrite_fallback=False,
            hits=[],
            answer=None,
            status=failure.log_status,
            error_stage=None,
            error_message="cancelled before start",
            duration_ms=int((time.perf_counter() - started) * 1000),
            model=client.model,
        )
        return

    graph = build_ask_graph(client, cancel=cancel)
    initial: AskState = {
        "original_query": original,
        "optimized_query": original,
        "top_k": top_k,
        "source_path": source_path,
        "title": title,
        "updated_at": updated_at,
        "hits": [],
        "total": 0,
        "answer": "",
        "ok": True,
        "rewrite_fallback": False,
        "error_stage": None,
        "error_message": None,
        "rewrite_enabled": True,
        "retrieve_round": 1,
    }

    # 从流式事件里汇总日志字段
    optimized_query = original
    rewrite_fallback = False
    hits: list[dict[str, Any]] = []
    answer: str | None = None
    status = "success"
    error_stage: str | None = None
    error_message: str | None = None
    terminal_events: list[dict[str, Any]] = []
    saw_done = False

    try:
        async for mode, chunk in graph.astream(
            initial,
            stream_mode=["custom", "values"],
        ):
            if cancel is not None:
                cancel.throw_if_cancelled()

            if mode == "custom" and isinstance(chunk, dict):
                event_type = chunk.get("type")
                if event_type == "rewrite_done":
                    optimized_query = chunk.get("optimized_query") or optimized_query
                    rewrite_fallback = bool(chunk.get("fallback"))
                elif event_type == "retrieve_done":
                    hits = list(chunk.get("hits") or [])
                elif event_type == "answer_done":
                    answer = chunk.get("answer")
                elif event_type == "error":
                    status = "error"
                    error_stage = chunk.get("stage") or error_stage
                    error_message = chunk.get("message") or error_message
                    # rewrite fallback 不算整次失败
                    if chunk.get("fallback"):
                        status = "success"
                        error_stage = None
                        error_message = None
                elif event_type == "done":
                    saw_done = True
                    if chunk.get("ok") is False:
                        status = "error"

                yield _sse(chunk)

            elif mode == "values" and isinstance(chunk, dict):
                if chunk.get("optimized_query"):
                    optimized_query = chunk["optimized_query"]
                if "rewrite_fallback" in chunk:
                    rewrite_fallback = bool(chunk["rewrite_fallback"])
                if chunk.get("hits") is not None:
                    hits = list(chunk["hits"] or [])
                if chunk.get("answer"):
                    answer = chunk["answer"]
                if chunk.get("ok") is False:
                    status = "error"
                    error_stage = chunk.get("error_stage") or error_stage
                    error_message = chunk.get("error_message") or error_message
    except Exception as exc:  # noqa: BLE001
        # 图内未包住的异常：尽量补 error + done，让前端有明确收尾
        failure = classify_ask_exception(exc, cancel=cancel)
        status = failure.log_status
        if failure.is_cancelled:
            error_stage = None
            error_message = "cancelled by client"
            if not saw_done:
                terminal_events.append(build_done_event(failure, ok=False))
        else:
            error_stage = error_stage or "stream"
            error_message = failure.message
            if not saw_done:
                terminal_events.append(build_error_event(error_stage, failure))
                terminal_events.append(build_done_event(failure, ok=False))
    finally:
        # 必须在继续 yield 前写库：消费者断开时后续 yield 可能触发 GeneratorExit
        _persist_ask_log(
            db,
            user_id=user_id,
            original_query=original,
            optimized_query=optimized_query,
            rewrite_fallback=rewrite_fallback,
            hits=hits,
            answer=answer,
            status=status,
            error_stage=error_stage,
            error_message=error_message,
            duration_ms=int((time.perf_counter() - started) * 1000),
            model=client.model,
        )

    # 图正常跑完却漏了 done：补一帧，避免前端只能靠断连兜底
    if not saw_done and not terminal_events:
        if status == "error":
            failure = AskFailure(
                kind="error",
                code="unexpected",
                message=error_message or "回答未正常结束",
            )
            terminal_events.append(
                build_error_event(error_stage or "stream", failure)
            )
            terminal_events.append(build_done_event(failure, ok=False))
        else:
            terminal_events.append({"type": "done", "ok": True})

    for event in terminal_events:
        yield _sse(event)
