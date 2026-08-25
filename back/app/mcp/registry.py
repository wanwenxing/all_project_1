"""MCP 工具注册表：新增工具时在此挂载。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.mcp.tools.math import add, multiply

# (name, callable) — 仅注册到 MCP Server；Agent 经 MCP Client 发现
TOOL_FUNCTIONS: list[tuple[str, Callable[..., Any]]] = [
    ("multiply", multiply),
    ("add", add),
]


def iter_tool_functions() -> list[tuple[str, Callable[..., Any]]]:
    return list(TOOL_FUNCTIONS)
