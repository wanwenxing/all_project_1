"""评测 LLM-as-Judge：对照期望给 Ask 结果打分。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.client import DeepSeekChatClient

REVIEW_SCORE_THRESHOLD = 60

JUDGE_SYSTEM = (
    "你是知识库问答评测裁判。根据「用户问题、期望、实际回答、检索命中」给出 0-100 分。\n"
    "评分关注：\n"
    "1) 检索是否命中期望文档（路径/标题相关即可）\n"
    "2) 回答是否覆盖期望要点，且有材料依据、少幻觉\n"
    "3) 材料不足时应拒答或说明无法得出结论\n"
    "只输出一个 JSON 对象，不要 Markdown 代码块，不要其它说明。格式：\n"
    '{"score":0-100,"reason":"简短中文理由","retrieval_ok":true/false}'
)


def _hits_brief(hits: list[dict[str, Any]], *, limit: int = 5) -> str:
    if not hits:
        return "（无命中）"
    lines: list[str] = []
    for i, hit in enumerate(hits[:limit], start=1):
        title = hit.get("title") or "未命名"
        path = hit.get("source_path") or "-"
        content = (hit.get("content") or "").strip().replace("\n", " ")
        if len(content) > 120:
            content = content[:120] + "…"
        lines.append(f"[{i}] 标题={title} 路径={path}\n{content}")
    return "\n".join(lines)


def _rule_retrieval_ok(expected_doc: str | None, hits: list[dict[str, Any]]) -> bool | None:
    """期望文档是否出现在 hits 中；无期望则返回 None。"""
    needle = (expected_doc or "").strip().lower()
    if not needle:
        return None
    for hit in hits:
        path = str(hit.get("source_path") or "").lower()
        title = str(hit.get("title") or "").lower()
        if needle in path or needle in title or path in needle or title in needle:
            return True
    return False


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("空响应")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(raw[start : end + 1])
        if isinstance(data, dict):
            return data
    raise ValueError(f"无法解析 Judge JSON: {text[:200]}")


async def judge_ask_result(
    llm: DeepSeekChatClient,
    *,
    query: str,
    expected_doc: str | None,
    expected_points: str | None,
    answer: str | None,
    hits: list[dict[str, Any]],
    ask_status: str = "success",
) -> dict[str, Any]:
    """返回 score/reason/retrieval_ok/needs_review/passed。"""
    if ask_status != "success":
        return {
            "score": 0,
            "reason": f"问答未成功（status={ask_status}），不计有效回答分",
            "retrieval_ok": False,
            "needs_review": True,
            "passed": False,
        }

    rule_hit = _rule_retrieval_ok(expected_doc, hits)
    user = (
        f"用户问题：\n{query.strip()}\n\n"
        f"期望文档：\n{(expected_doc or '（未标注）').strip()}\n\n"
        f"期望要点：\n{(expected_points or '（未标注）').strip()}\n\n"
        f"实际检索命中：\n{_hits_brief(hits)}\n\n"
        f"规则检索命中判定：{rule_hit if rule_hit is not None else '无期望文档，跳过'}\n\n"
        f"实际回答：\n{(answer or '（空）').strip()}\n"
    )

    raw = await llm.chat(system=JUDGE_SYSTEM, user=user, temperature=0.1)
    data = _extract_json_object(raw)
    score_raw = data.get("score", 0)
    try:
        score = int(round(float(score_raw)))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    reason = str(data.get("reason") or "").strip() or "（无理由）"
    retrieval_ok = data.get("retrieval_ok")
    if not isinstance(retrieval_ok, bool):
        retrieval_ok = bool(rule_hit) if rule_hit is not None else False
    # 规则未命中时期望文档明确时，机评分上限压到 59，强制进复核
    if rule_hit is False and score >= REVIEW_SCORE_THRESHOLD:
        score = REVIEW_SCORE_THRESHOLD - 1
        reason = f"期望文档未命中；{reason}"

    needs_review = score < REVIEW_SCORE_THRESHOLD
    passed = (not needs_review) and (rule_hit is not False)
    return {
        "score": score,
        "reason": reason,
        "retrieval_ok": retrieval_ok,
        "needs_review": needs_review,
        "passed": passed,
    }
