"""全局 LLM 连接封装（与具体 RAG 业务解耦）。"""

from app.core.ask_errors import LLMNotConfiguredError, LLMTimeoutError
from app.llm.client import DeepSeekChatClient, get_llm_client

__all__ = [
    "DeepSeekChatClient",
    "LLMNotConfiguredError",
    "LLMTimeoutError",
    "get_llm_client",
]
