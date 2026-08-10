from __future__ import annotations

from typing import Any, TypedDict

import anyio
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.llm import DeepSeekChatClient
from app.llm.ask_llm import answer_from_hits_stream, rewrite_query_stream
from app.services.docs import search_knowledge_base


class AskState(TypedDict, total=False):
    original_query: str
    optimized_query: str
    top_k: int
    source_path: str | None
    title: str | None
    updated_at: str | None
    hits: list[dict[str, Any]]
    total: int
    answer: str
    ok: bool
    rewrite_fallback: bool
    error_stage: str | None
    error_message: str | None
    # 预留扩展
    rewrite_enabled: bool
    retrieve_round: int


def build_ask_graph(llm: DeepSeekChatClient):
    """线性图：rewrite → retrieve → answer。"""

    async def rewrite_node(state: AskState) -> dict[str, Any]:
        writer = get_stream_writer()
        original = (state.get("original_query") or "").strip()
        writer({"type": "stage", "stage": "rewrite", "status": "start"})

        optimized = original
        rewrite_fallback = False
        try:
            chunks: list[str] = []
            async for delta in rewrite_query_stream(llm, original):
                chunks.append(delta)
                writer({"type": "rewrite_delta", "delta": delta})
            rewritten = "".join(chunks).strip()
            if rewritten:
                optimized = rewritten
        except Exception as exc:  # noqa: BLE001
            rewrite_fallback = True
            writer(
                {
                    "type": "error",
                    "stage": "rewrite",
                    "message": f"问题优化失败，将使用原问题继续：{exc}",
                    "fallback": True,
                }
            )

        writer(
            {
                "type": "rewrite_done",
                "original_query": original,
                "optimized_query": optimized,
                "fallback": rewrite_fallback,
            }
        )
        writer({"type": "stage", "stage": "rewrite", "status": "done"})
        return {
            "optimized_query": optimized,
            "rewrite_fallback": rewrite_fallback,
        }

    async def retrieve_node(state: AskState) -> dict[str, Any]:
        writer = get_stream_writer()
        optimized = (state.get("optimized_query") or state.get("original_query") or "").strip()
        writer({"type": "stage", "stage": "retrieve", "status": "start"})

        try:
            search_result = await anyio.to_thread.run_sync(
                lambda: search_knowledge_base(
                    query=optimized,
                    top_k=int(state.get("top_k") or 2),
                    source_path=state.get("source_path"),
                    title=state.get("title"),
                    updated_at=state.get("updated_at"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            writer({"type": "error", "stage": "retrieve", "message": message})
            return {
                "hits": [],
                "total": 0,
                "ok": False,
                "error_stage": "retrieve",
                "error_message": message,
            }

        hits = search_result.get("hits") or []
        total = int(search_result.get("total", len(hits)))
        writer(
            {
                "type": "retrieve_done",
                "query": optimized,
                "total": total,
                "hits": hits,
            }
        )
        writer({"type": "stage", "stage": "retrieve", "status": "done"})
        return {
            "hits": hits,
            "total": total,
            "ok": True,
            "error_stage": None,
            "error_message": None,
        }

    async def answer_node(state: AskState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer({"type": "stage", "stage": "answer", "status": "start"})
        original = (state.get("original_query") or "").strip()
        optimized = (state.get("optimized_query") or original).strip()
        hits = state.get("hits") or []

        answer_parts: list[str] = []
        try:
            async for delta in answer_from_hits_stream(
                llm,
                original_query=original,
                optimized_query=optimized,
                hits=hits,
            ):
                answer_parts.append(delta)
                writer({"type": "answer_delta", "delta": delta})
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            writer({"type": "error", "stage": "answer", "message": message})
            writer({"type": "done", "ok": False})
            return {
                "answer": "".join(answer_parts),
                "ok": False,
                "error_stage": "answer",
                "error_message": message,
            }

        answer = "".join(answer_parts)
        writer({"type": "answer_done", "answer": answer})
        writer({"type": "stage", "stage": "answer", "status": "done"})
        writer(
            {
                "type": "done",
                "ok": True,
                "original_query": original,
                "optimized_query": optimized,
                "total": len(hits),
            }
        )
        return {"answer": answer, "ok": True}

    def route_after_retrieve(state: AskState) -> str:
        if state.get("ok") is False and state.get("error_stage") == "retrieve":
            return "finish_error"
        return "answer"

    async def finish_error_node(state: AskState) -> dict[str, Any]:
        # retrieve 失败时已在 retrieve_node 写过 error；此处补 done
        writer = get_stream_writer()
        writer({"type": "done", "ok": False})
        return {"ok": False}

    graph = StateGraph(AskState)
    graph.add_node("rewrite", rewrite_node) # 问题优化节点
    graph.add_node("retrieve", retrieve_node) # 向量检索节点
    graph.add_node("answer", answer_node) # 答案生成节点
    graph.add_node("finish_error", finish_error_node) # 错误处理节点

    graph.add_edge(START, "rewrite")
    graph.add_edge("rewrite", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"answer": "answer", "finish_error": "finish_error"},
    )
    graph.add_edge("answer", END)
    graph.add_edge("finish_error", END)
    return graph.compile()
