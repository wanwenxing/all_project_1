"""Agent 图节点：ChatOpenAI.bind_tools 决策是否发起 tool_calls。"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

DEFAULT_AGENT_SYSTEM = (
    "你是一个可调用工具的智能助手。需要计算或查数时优先使用工具；"
    "工具结果返回后，用简洁中文给出最终回答。"
)


async def agent_node(
    state: dict[str, Any],
    *,
    llm: BaseChatModel,
    tools: list[Any],
    system_prompt: str = DEFAULT_AGENT_SYSTEM,
) -> dict[str, Any]:
    """根据对话决定是否发起 tool_calls，供后续 call_tools 节点执行。"""
    messages = list(state.get("messages") or [])
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_prompt), *messages]

    runnable = llm.bind_tools(tools) if tools else llm
    response = await runnable.ainvoke(messages)
    return {"messages": [response]}
