from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import APITimeoutError, AsyncOpenAI

from app.core.ask_cancel import AskCancelled, AskCancelToken
from app.core.ask_errors import LLMNotConfiguredError, LLMTimeoutError
from app.core.config import settings


async def _aclose_stream(stream: Any) -> None:
    close = getattr(stream, "close", None) or getattr(stream, "aclose", None)
    if close is None:
        return
    result = close()
    if hasattr(result, "__await__"):
        await result


class DeepSeekChatClient:
    """全局 DeepSeek / OpenAI 兼容连接封装，不含具体业务 prompt。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.llm_api_key).strip()
        self.base_url = base_url or settings.llm_base_url
        self.model = model or settings.llm_model
        self.timeout = timeout if timeout is not None else settings.llm_timeout_seconds
        self._client = client

    def ensure_configured(self) -> None:
        if not self.api_key:
            raise LLMNotConfiguredError("未配置 LLM_API_KEY，无法调用 DeepSeek")

    def _get_client(self) -> AsyncOpenAI:
        self.ensure_configured()
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def stream_chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        disable_thinking: bool = True,
        cancel: AskCancelToken | None = None,
    ) -> AsyncIterator[str]:
        """通用流式 chat.completions；默认关闭思考模式，仅产出正文 content。

        取消 → AskCancelled；超时 → LLMTimeoutError；其它异常原样上抛。
        """
        if cancel is not None:
            cancel.throw_if_cancelled()

        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        stream = None
        try:
            if disable_thinking:
                try:
                    stream = await client.chat.completions.create(
                        **kwargs,
                        extra_body={"thinking": {"type": "disabled"}},
                    )
                except TypeError:
                    # 旧版 SDK 不支持 extra_body 时退回普通调用
                    stream = await client.chat.completions.create(**kwargs)
            else:
                stream = await client.chat.completions.create(**kwargs)

            async for chunk in stream:
                if cancel is not None:
                    cancel.throw_if_cancelled()
                choice = chunk.choices[0] if chunk.choices else None
                if choice is None or choice.delta is None:
                    continue
                content = choice.delta.content
                if content:
                    yield content
        except AskCancelled:
            raise
        except APITimeoutError as exc:
            raise LLMTimeoutError(
                f"模型响应超时（>{self.timeout:.0f}s），请稍后重试"
            ) from exc
        finally:
            if stream is not None:
                await _aclose_stream(stream)

    async def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.1,
        disable_thinking: bool = True,
    ) -> str:
        """非流式 chat，适合 Judge 等需要完整 JSON 的场景。"""
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            if disable_thinking:
                try:
                    resp = await client.chat.completions.create(
                        **kwargs,
                        extra_body={"thinking": {"type": "disabled"}},
                    )
                except TypeError:
                    resp = await client.chat.completions.create(**kwargs)
            else:
                resp = await client.chat.completions.create(**kwargs)
        except APITimeoutError as exc:
            raise LLMTimeoutError(
                f"模型响应超时（>{self.timeout:.0f}s），请稍后重试"
            ) from exc

        choice = resp.choices[0] if resp.choices else None
        content = choice.message.content if choice and choice.message else None
        return (content or "").strip()


def get_llm_client() -> DeepSeekChatClient:
    return DeepSeekChatClient()
