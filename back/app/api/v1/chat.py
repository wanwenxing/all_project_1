import asyncio
import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.ask_cancel import AskCancelToken
from app.core.ask_errors import build_done_event, build_error_event, classify_ask_exception
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.chat import (
    ChatMessageData,
    ChatMessageRequest,
    ChatSessionCreate,
    ChatSessionData,
)
from app.schemas.common import ApiResponse, success
from app.services import memory_chat as memory_chat_service

router = APIRouter()


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _user_key(user: User) -> str:
    return str(user.id)


async def _watch_disconnect(request: Request, cancel: AskCancelToken) -> None:
    try:
        while not cancel.is_cancelled:
            try:
                disconnected = await asyncio.wait_for(request.is_disconnected(), timeout=0.3)
            except (asyncio.TimeoutError, Exception):
                disconnected = False
            if disconnected:
                cancel.cancel()
                return
            await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        return


@router.post("/sessions", response_model=ApiResponse[ChatSessionData])
def create_chat_session(
    payload: ChatSessionCreate | None = None,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ChatSessionData]:
    title = payload.title if payload else None
    session = memory_chat_service.create_session(_user_key(current_user), title)
    return success(ChatSessionData(**session), message="会话已创建")


@router.get("/sessions", response_model=ApiResponse[list[ChatSessionData]])
def list_chat_sessions(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[ChatSessionData]]:
    sessions = memory_chat_service.list_sessions(_user_key(current_user))
    return success([ChatSessionData(**s) for s in sessions], message="ok")


@router.delete("/sessions/{thread_id}", response_model=ApiResponse[None])
def delete_chat_session(
    thread_id: str,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[None]:
    ok = memory_chat_service.delete_session(_user_key(current_user), thread_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return success(None, message="会话已删除")


@router.get("/sessions/{thread_id}/messages", response_model=ApiResponse[list[ChatMessageData]])
async def list_chat_messages(
    thread_id: str,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[ChatMessageData]]:
    messages = await memory_chat_service.get_session_messages(
        _user_key(current_user),
        thread_id,
    )
    return success([ChatMessageData(**msg) for msg in messages], message="ok")


@router.post("")
async def memory_chat(
    request: Request,
    payload: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE：短期 thread 记忆 + 长期 user 记忆（BGE + DeepSeek）。"""

    async def event_generator():
        cancel = AskCancelToken()
        watcher = asyncio.create_task(_watch_disconnect(request, cancel))
        try:
            try:
                async for frame in memory_chat_service.memory_chat_stream(
                    user_id=_user_key(current_user),
                    thread_id=payload.thread_id,
                    message=payload.message,
                    cancel=cancel,
                ):
                    yield _sse(frame)
                    if cancel.is_cancelled:
                        break
            except Exception as exc:  # noqa: BLE001
                failure = classify_ask_exception(exc, cancel=cancel)
                if failure.is_cancelled:
                    yield _sse(build_done_event(failure, ok=False))
                else:
                    yield _sse(build_error_event("stream", failure))
                    yield _sse(build_done_event(failure, ok=False))
        finally:
            cancel.cancel()
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
