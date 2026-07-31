"""全局 LLM 连接封装（与具体 RAG 业务解耦）。"""

from app.llm.client import DeepSeekChatClient, LLMNotConfiguredError, get_llm_client

__all__ = [
    "DeepSeekChatClient",
    "LLMNotConfiguredError",
    "get_llm_client",
]
