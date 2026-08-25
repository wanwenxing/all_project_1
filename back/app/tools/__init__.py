"""兼容层：转发到 Agent 侧 MCP Client。"""

from app.agent.mcp_tools import load_tools_from_mcp

__all__ = ["load_tools_from_mcp"]
