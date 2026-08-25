"""MCP 包：常驻 Server。

启动::

    uv run python -m app.mcp
    uv run python run_mcp.py

Agent 通过 ``app.agent.mcp_tools.load_tools_from_mcp`` 连接 ``MCP_URL``。
"""

from app.mcp.server import main, mcp

__all__ = ["main", "mcp"]
