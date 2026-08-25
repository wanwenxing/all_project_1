"""Agent 图对外运行：经 MCP Client 拉 tools 后编译并 ainvoke。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import build_agent_graph

_graph = None


async def get_compiled_agent_graph():
    global _graph
    if _graph is None:
        _graph = await build_agent_graph()
    return _graph


def reset_agent_graph_for_tests() -> None:
    global _graph
    _graph = None


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


def _extract_result(messages: list[Any]) -> dict[str, Any]:
    tool_steps: list[dict[str, str]] = []
    answer = ""

    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_steps.append(
                {
                    "name": str(getattr(msg, "name", None) or "tool"),
                    "content": _message_text(msg.content),
                }
            )
        elif isinstance(msg, AIMessage):
            text = _message_text(msg.content).strip()
            if text and not getattr(msg, "tool_calls", None):
                answer = text

    if not answer:
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                text = _message_text(msg.content).strip()
                if text:
                    answer = text
                    break

    return {"answer": answer or "", "tool_steps": tool_steps}


async def run_agent(
    message: str,
    *,
    graph=None,
    recursion_limit: int = 16,
) -> dict[str, Any]:
    """运行 Agent 图，返回最终回答与工具步骤。"""
    compiled = graph or await get_compiled_agent_graph()
    result = await compiled.ainvoke(
        {"messages": [HumanMessage(content=message.strip())]},
        config={"recursion_limit": recursion_limit},
    )
    return _extract_result(list(result.get("messages") or []))
