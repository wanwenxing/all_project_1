"""工具调用后的条件路由（具体策略后续补充）。"""

from __future__ import annotations

from typing import Literal

from app.agent.state import AgentState

# 路由目标节点名；后续按工具类型 / 业务规则扩展 path_map
RouteAfterTools = Literal["agent"]


def route_after_tools(state: AgentState) -> RouteAfterTools:
    """call_tools 之后的边选择。

    当前为占位实现：一律回到 agent，形成 ReAct 循环。
    后续可按 tool 名称、route_hint、业务规则路由到不同节点。
    """
    _ = state  # 预留：读取 messages / route_hint 做分支
    return "agent"
