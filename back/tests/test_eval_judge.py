import asyncio

from app.llm.eval_judge import (
    REVIEW_SCORE_THRESHOLD,
    _extract_json_object,
    _rule_retrieval_ok,
    judge_ask_result,
)


def test_extract_json_object_plain_and_fenced():
    assert _extract_json_object('{"score": 80, "reason": "ok"}')["score"] == 80
    data = _extract_json_object('说明如下\n```json\n{"score": 70, "reason": "x"}\n```')
    assert data["score"] == 70


def test_rule_retrieval_ok():
    hits = [{"source_path": "docs/友情.md", "title": "友情"}]
    assert _rule_retrieval_ok("docs/友情.md", hits) is True
    assert _rule_retrieval_ok("友情", hits) is True
    assert _rule_retrieval_ok("docs/其他.md", hits) is False
    assert _rule_retrieval_ok(None, hits) is None


def test_judge_ask_result_caps_score_when_doc_miss():
    class FakeLLM:
        async def chat(self, **_kwargs):
            return '{"score": 90, "reason": "看起来不错", "retrieval_ok": true}'

    judged = asyncio.run(
        judge_ask_result(
            FakeLLM(),  # type: ignore[arg-type]
            query="q",
            expected_doc="docs/友情.md",
            expected_points="要点",
            answer="答",
            hits=[{"source_path": "docs/其他.md", "title": "其他"}],
            ask_status="success",
        )
    )
    assert judged["score"] == REVIEW_SCORE_THRESHOLD - 1
    assert judged["needs_review"] is True
    assert judged["passed"] is False
