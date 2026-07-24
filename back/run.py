#!/usr/bin/env python3
"""Run the FastAPI development server."""

from pathlib import Path

import uvicorn

from app.core.config import settings

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    # 只监视 app/，避免 .venv / data / 模型缓存触发热重载把 embedding 模型卸掉
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_dirs=[str(ROOT / "app")] if settings.debug else None,
    )
