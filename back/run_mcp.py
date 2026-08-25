#!/usr/bin/env python3
"""启动 MCP 常驻服务（独立于 FastAPI）。"""

from app.mcp.server import main

if __name__ == "__main__":
    main()
