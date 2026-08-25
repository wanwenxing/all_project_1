"""Agent 侧 MCP Client：连接常驻 MCP HTTP 服务拉取 tools。"""

from __future__ import annotations

from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.core.config import settings

_client: MultiServerMCPClient | None = None
_tools_cache: list[Any] | None = None


def _http_connection() -> dict[str, Any]:
    return {
        "transport": "streamable_http",
        "url": settings.mcp_url,
    }


def _get_mcp_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        _client = MultiServerMCPClient({"back-tools": _http_connection()})
    return _client


async def load_tools_from_mcp(*, force_reload: bool = False) -> list[Any]:
    """连接已启动的 MCP 常驻服务，发现并加载 LangChain tools。"""
    global _tools_cache
    if _tools_cache is not None and not force_reload:
        return _tools_cache
    _tools_cache = await _get_mcp_client().get_tools()
    return _tools_cache


def reset_mcp_tools_for_tests() -> None:
    global _client, _tools_cache
    _client = None
    _tools_cache = None
