"""Agent 智能编排图：agent → call_tools → 条件路由。"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.llm import get_agent_llm
from app.agent.mcp_tools import load_tools_from_mcp
from app.agent.nodes import agent_node
from app.agent.routing import route_after_tools
from app.agent.state import AgentState


async def build_agent_graph(
    llm: BaseChatModel | None = None,
    *,
    tools: list[Any] | None = None,
):
    """构建具备 call_tools 与路由边选择的 Agent 图。

    默认通过 MCP Client 从 ``app.mcp`` Server 拉取 tools；
    测试或自定义场景可传入 ``tools`` 跳过 MCP。
    """
    llm = llm or get_agent_llm()
    tools = tools if tools is not None else await load_tools_from_mcp()

    async def _agent(state: AgentState) -> dict[str, Any]:
        return await agent_node(state, llm=llm, tools=tools)

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", _agent)
    workflow.add_node("call_tools", ToolNode(tools))

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "call_tools", END: END},
    )
    workflow.add_conditional_edges(
        "call_tools",
        route_after_tools,
        {"agent": "agent"},
    )

    return workflow.compile()
