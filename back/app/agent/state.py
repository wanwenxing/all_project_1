"""Agent 图状态。"""

from __future__ import annotations

from typing import Annotated, Optional, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # 预留给后续路由 / 评分等扩展
    route_hint: Annotated[Optional[str], "Optional hint for post-tool routing"]
