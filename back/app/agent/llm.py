"""Agent 专用 LLM：langchain-openai ChatOpenAI 对接 DeepSeek 兼容接口。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_agent_llm(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: float | None = None,
) -> ChatOpenAI:
    """创建绑定工具能力的 Chat 模型（Ask SSE 仍用自研 DeepSeekChatClient）。"""
    return ChatOpenAI(
        api_key=api_key if api_key is not None else settings.llm_api_key,
        base_url=base_url or settings.llm_base_url,
        model=model or settings.llm_model,
        temperature=temperature,
        timeout=timeout if timeout is not None else settings.llm_timeout_seconds,
        # DeepSeek 兼容网关：关闭思考模式，只保留正文
        extra_body={"thinking": {"type": "disabled"}},
    )
