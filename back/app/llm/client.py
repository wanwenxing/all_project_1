from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings


class LLMNotConfiguredError(RuntimeError):
    """Raised when LLM_API_KEY is missing."""


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
    ) -> AsyncIterator[str]:
        """通用流式 chat.completions；默认关闭思考模式，仅产出正文 content。"""
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
        if disable_thinking:
            try:
                stream = await client.chat.completions.create(
                    **kwargs,
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except TypeError:
                stream = await client.chat.completions.create(**kwargs)
        else:
            stream = await client.chat.completions.create(**kwargs)

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None or choice.delta is None:
                continue
            content = choice.delta.content
            if content:
                yield content


def get_llm_client() -> DeepSeekChatClient:
    return DeepSeekChatClient()
