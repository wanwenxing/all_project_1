"""RAG /ask 业务侧的 prompt 与流式调用（依赖通用 LLM 客户端，不含连接细节）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.llm.client import DeepSeekChatClient

REWRITE_SYSTEM = (
    "你是检索查询改写助手。把用户问题改写成更利于向量检索的精简中文问句。"
    "只输出改写后的问句本身，不要解释、不要引号、不要前后缀。"
)

ANSWER_SYSTEM = (
    "你是个人知识库问答助手。只能依据提供的检索材料回答用户问题；"
    "材料不足时明确说明无法从知识库得出结论，不要编造。"
    "回答使用简洁中文，必要时在文末用一两行列出来源标题或路径。"
)


def format_hits(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "（无命中材料）"

    parts: list[str] = []
    for index, hit in enumerate(hits, start=1):
        title = hit.get("title") or "未命名"
        source = hit.get("source_path") or ""
        content = (hit.get("content") or "").strip()
        score = hit.get("score")
        score_text = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
        parts.append(
            f"[{index}] 标题={title} 路径={source} 相关度={score_text}\n{content}"
        )
    return "\n\n".join(parts)


async def rewrite_query_stream(
    llm: DeepSeekChatClient,
    original: str,
) -> AsyncIterator[str]:
    user = f"用户原问题：\n{original.strip()}"
    async for delta in llm.stream_chat(
        system=REWRITE_SYSTEM,
        user=user,
        temperature=0.1,
    ):
        yield delta


async def answer_from_hits_stream(
    llm: DeepSeekChatClient,
    *,
    original_query: str,
    optimized_query: str,
    hits: list[dict[str, Any]],
) -> AsyncIterator[str]:
    materials = format_hits(hits)
    user = (
        f"用户原问题：{original_query.strip()}\n"
        f"检索用问题：{optimized_query.strip()}\n\n"
        f"检索材料：\n{materials}\n\n"
        "请基于上述材料作答。"
    )
    async for delta in llm.stream_chat(
        system=ANSWER_SYSTEM,
        user=user,
        temperature=0.3,
    ):
        yield delta
