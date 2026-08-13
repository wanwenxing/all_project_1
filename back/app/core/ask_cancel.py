"""Ask / SSE 协作取消：前端 abort 断连后，后端用同一 token 停掉编排和 LLM 流。"""

from __future__ import annotations

import asyncio


class AskCancelled(Exception):
    """用户取消本次 Ask（不是业务 error）。"""


class AskCancelToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def throw_if_cancelled(self) -> None:
        """检查任务是否已取消，如果已取消则抛出异常。

        Args:
            self: 当前实例

        Raises:
            AskCancelled: 当任务被客户端取消时抛出
        """
        if self._event.is_set():
            raise AskCancelled("ask cancelled by client")
