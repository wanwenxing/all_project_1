"""RAG /ask 业务侧的 prompt 与流式调用（依赖通用 LLM 客户端，不含连接细节）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.ask_cancel import AskCancelToken
from app.llm.client import DeepSeekChatClient

REWRITE_SYSTEM = (
    "你是检索查询改写助手。把用户问题改写成更利于向量检索的精简中文问句。"
    "只输出改写后的问句本身，不要解释、不要引号、不要前后缀。"
)

ANSWER_HEADER = "【回答】"
EVIDENCE_HEADER = "【依据材料】"

ANSWER_SYSTEM = (
    "你是个人知识库问答助手。只能依据提供的检索材料回答用户问题；"
    "材料不足时明确说明无法从知识库得出结论，不要编造。\n"
    "必须严格按以下结构输出，不要增加其它标题或前后缀：\n"
    f"{ANSWER_HEADER}\n"
    "<简洁中文答案；关键事实用材料编号标注，如 [1]、[2]>\n"
    f"{EVIDENCE_HEADER}\n"
    "<只列出你实际用到的材料，每条一行："
    "[编号] 标题=... 路径=...；摘录：<相关原文一句>>\n"
    "若无可用材料，依据材料处写「（无命中材料）」。"
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


def format_evidence_block(hits: list[dict[str, Any]]) -> str:
    """用 hits 生成稳定的文末原文依据块（不依赖模型是否写全）。"""
    if not hits:
        return f"{EVIDENCE_HEADER}\n（无命中材料）"

    lines = [EVIDENCE_HEADER]
    for index, hit in enumerate(hits, start=1):
        title = hit.get("title") or "未命名"
        source = hit.get("source_path") or "-"
        content = (hit.get("content") or "").strip().replace("\n", " ")
        if len(content) > 160:
            content = content[:160].rstrip() + "…"
        lines.append(f"[{index}] 标题={title} 路径={source}；摘录：{content or '（空）'}")
    return "\n".join(lines)


def ensure_answer_with_evidence(answer: str, hits: list[dict[str, Any]]) -> str:
    """保证最终回答含【依据材料】；模型漏写时用 hits 补上。"""
    text = (answer or "").strip()
    evidence = format_evidence_block(hits)

    if EVIDENCE_HEADER in text:
        # 模型已带结构：若只有依据块没有回答标题，仍原样返回
        if ANSWER_HEADER not in text:
            return f"{ANSWER_HEADER}\n{text}"
        return text

    body = text
    if body.startswith(ANSWER_HEADER):
        body = body[len(ANSWER_HEADER) :].lstrip("\n")
    if body:
        return f"{ANSWER_HEADER}\n{body}\n\n{evidence}"
    return f"{ANSWER_HEADER}\n（未能生成有效回答）\n\n{evidence}"


def public_sources(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """结构化凭据，供 SSE / 前端展示。"""
    sources: list[dict[str, Any]] = []
    for index, hit in enumerate(hits, start=1):
        sources.append(
            {
                "index": index,
                "title": hit.get("title"),
                "source_path": hit.get("source_path"),
                "content": hit.get("content"),
                "score": hit.get("score"),
                "chroma_id": hit.get("chroma_id"),
                "document_id": hit.get("document_id"),
                "chunk_id": hit.get("chunk_id"),
                "chunk_index": hit.get("chunk_index"),
            }
        )
    return sources


async def rewrite_query_stream(
    llm: DeepSeekChatClient,
    original: str,
    *,
    cancel: AskCancelToken | None = None,
) -> AsyncIterator[str]:
    user = f"用户原问题：\n{original.strip()}"
    async for delta in llm.stream_chat(
        system=REWRITE_SYSTEM,
        user=user,
        temperature=0.1,
        cancel=cancel,
    ):
        yield delta


async def answer_from_hits_stream(
    llm: DeepSeekChatClient,
    *,
    original_query: str,
    optimized_query: str,
    hits: list[dict[str, Any]],
    cancel: AskCancelToken | None = None,
) -> AsyncIterator[str]:
    materials = format_hits(hits)
    user = (
        f"用户原问题：{original_query.strip()}\n"
        f"检索用问题：{optimized_query.strip()}\n\n"
        f"检索材料（编号供引用）：\n{materials}\n\n"
        f"请按「{ANSWER_HEADER} / {EVIDENCE_HEADER}」结构作答，并在结尾附上所用原文信息。"
    )
    async for delta in llm.stream_chat(
        system=ANSWER_SYSTEM,
        user=user,
        temperature=0.2,
        cancel=cancel,
    ):
        yield delta
