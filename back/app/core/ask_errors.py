"""Ask / SSE 异常集中定义与分类。

流式链路里常见几类失败：
- cancelled：用户取消 / 连接断开
- timeout：LLM 调用超时
- config：未配置 API Key 等
- error：其它业务/未知异常

节点与 ask 编排只依赖 classify + build_*_event，避免到处复制 except 分支。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.ask_cancel import AskCancelled, AskCancelToken

AskErrorKind = Literal["cancelled", "timeout", "config", "error"]


class LLMNotConfiguredError(RuntimeError):
    """未配置 LLM_API_KEY。"""


class LLMTimeoutError(TimeoutError):
    """LLM 调用超过配置的 timeout。"""

    def __init__(self, message: str = "模型响应超时，请稍后重试") -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class AskFailure:
    kind: AskErrorKind
    message: str
    code: str | None = None
    """前端可识别的错误码，如 llm_timeout / cancelled。"""

    @property
    def log_status(self) -> str:
        return "cancelled" if self.kind == "cancelled" else "error"

    @property
    def is_cancelled(self) -> bool:
        return self.kind == "cancelled"


def classify_ask_exception(
    exc: BaseException,
    *,
    cancel: AskCancelToken | None = None,
) -> AskFailure:
    """把任意异常归成 Ask 统一失败模型。"""
    if isinstance(exc, AskCancelled) or (cancel is not None and cancel.is_cancelled):
        return AskFailure(
            kind="cancelled",
            code="cancelled",
            message="已取消",
        )
    if isinstance(exc, LLMTimeoutError):
        return AskFailure(
            kind="timeout",
            code="llm_timeout",
            message=exc.message,
        )
    if isinstance(exc, LLMNotConfiguredError):
        return AskFailure(
            kind="config",
            code="llm_not_configured",
            message=str(exc),
        )
    return AskFailure(
        kind="error",
        code="unexpected",
        message=str(exc) or exc.__class__.__name__,
    )


def build_error_event(
    stage: str,
    failure: AskFailure,
    *,
    fallback: bool = False,
    message: str | None = None,
) -> dict[str, Any]:
    """生成 SSE error 帧。"""
    payload: dict[str, Any] = {
        "type": "error",
        "stage": stage,
        "message": message if message is not None else failure.message,
        "fallback": fallback,
    }
    if failure.code:
        payload["code"] = failure.code
    return payload


def build_done_event(
    failure: AskFailure | None = None,
    *,
    ok: bool = False,
) -> dict[str, Any]:
    """生成 SSE done 帧。"""
    payload: dict[str, Any] = {"type": "done", "ok": ok}
    if failure is not None:
        if failure.is_cancelled:
            payload["cancelled"] = True
        if failure.code:
            payload["code"] = failure.code
    return payload
