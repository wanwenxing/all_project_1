"""back 项目 MCP 常驻服务入口（streamable-http）。

启动::

    uv run python -m app.mcp
    # 或
    uv run python run_mcp.py

默认监听 ``MCP_HOST:MCP_PORT``（如 0.0.0.0:3100），路径 ``/mcp``。
Agent / Cursor 等 Client 连接已启动的服务，而不会再按需拉起子进程。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.mcp.registry import iter_tool_functions

mcp = FastMCP(
    "back-tools",
    instructions="back 项目业务工具集（计算等）。通过 MCP 常驻 HTTP 服务对外暴露。",
    host=settings.mcp_host,
    port=settings.mcp_port,
    streamable_http_path="/mcp",
    # 无状态更适合多 Client 并发调用（Agent / IDE）
    stateless_http=True,
)

for _name, _fn in iter_tool_functions():
    mcp.tool(name=_name)(_fn)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
