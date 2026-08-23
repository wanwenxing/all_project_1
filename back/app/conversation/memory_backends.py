"""LangGraph 短期记忆：AsyncSqliteSaver 持久化 checkpoint。"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import settings

_checkpointer: AsyncSqliteSaver | None = None
_connection: aiosqlite.Connection | None = None


def _checkpoint_path() -> Path:
    path = Path(settings.memory_checkpoint_path)
    if not path.is_absolute():
        path = settings.back_root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


async def init_memory_backends() -> AsyncSqliteSaver:
    """应用启动时初始化 checkpoint 连接（仅调用一次）。"""
    global _checkpointer, _connection
    if _checkpointer is not None:
        return _checkpointer

    db_path = _checkpoint_path()
    _connection = await aiosqlite.connect(str(db_path))
    _checkpointer = AsyncSqliteSaver(_connection)
    return _checkpointer


def get_checkpointer() -> AsyncSqliteSaver:
    if _checkpointer is None:
        raise RuntimeError("记忆 checkpoint 未初始化，请先调用 init_memory_backends()")
    return _checkpointer


async def close_memory_backends() -> None:
    global _checkpointer, _connection
    _checkpointer = None
    if _connection is not None:
        await _connection.close()
        _connection = None


def reset_memory_backends_for_tests() -> None:
    """测试用：丢弃内存中的 checkpointer 引用（不关闭连接，由测试进程结束回收）。"""
    global _checkpointer, _connection
    _checkpointer = None
    _connection = None
