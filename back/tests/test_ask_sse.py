import json

from sqlalchemy import select

from app.core.config import settings
from app.db import session as db_session
from app.models.ask_log import AskLog
from app.llm import DeepSeekChatClient, LLMNotConfiguredError


def _auth_headers(client) -> dict[str, str]:
    payload = {
        "username": "askuser",
        "email": "ask@example.com",
        "password": "secret123",
    }
    client.post("/api/auth/register", json=payload)
    login = client.post(
        "/api/auth/login",
        json={"username": "askuser", "password": "secret123"},
    )
    token = login.json()["data"]["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block.startswith("data:"):
            continue
        payload = block[len("data:") :].strip()
        if payload:
            events.append(json.loads(payload))
    return events


class FakeLLM(DeepSeekChatClient):
    def __init__(self) -> None:
        super().__init__(api_key="fake-key", client=object())  # type: ignore[arg-type]

    def ensure_configured(self) -> None:
        return


async def _fake_rewrite(_llm, original: str, *, cancel=None):
    for part in ["优化:", original[:8]]:
        yield part


async def _fake_answer(_llm, *, original_query, optimized_query, hits, cancel=None):
    yield "根据材料："
    yield f"命中{len(hits)}条。"


async def _fake_rewrite_then_cancel(_llm, original: str, *, cancel=None):
    yield "优化中"
    if cancel is not None:
        cancel.cancel()
    from app.core.ask_cancel import AskCancelled

    raise AskCancelled("ask cancelled by client")


def test_ask_requires_auth(client):
    response = client.post("/api/docs/ask", json={"query": "友情"})
    assert response.status_code == 401


def test_ask_sse_event_order_and_log(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "fake-key")

    fake = FakeLLM()
    monkeypatch.setattr("app.services.ask.get_llm_client", lambda: fake)
    monkeypatch.setattr("app.rag.ask_graph.rewrite_query_stream", _fake_rewrite)
    monkeypatch.setattr("app.rag.ask_graph.answer_from_hits_stream", _fake_answer)
    monkeypatch.setattr(
        "app.rag.ask_graph.search_vector_hits",
        lambda **kwargs: [
            {
                "chroma_id": "chunk:1",
                "content": "长久胜过一般的爱情",
                "distance": 0.1,
                "score": 0.9,
                "document_id": "1",
                "chunk_id": "1",
                "chunk_index": 0,
                "source_path": "docs/友情.md",
                "title": "友情",
                "updated_at": "2026年6月",
            }
        ],
    )
    monkeypatch.setattr("app.rag.ask_graph.search_keyword_hits", lambda **kwargs: [])
    monkeypatch.setattr(
        "app.rag.ask_graph.fuse_hits",
        lambda vector_hits, keyword_hits, **kwargs: vector_hits[: kwargs.get("candidate_k", 5)],
    )
    monkeypatch.setattr(
        "app.rag.ask_graph.rerank_hits",
        lambda **kwargs: (kwargs.get("candidates") or [])[: kwargs.get("top_k", 2)],
    )
    monkeypatch.setattr(settings, "rag_hybrid_enabled", True)
    monkeypatch.setattr(settings, "rag_rerank_enabled", True)

    headers = _auth_headers(client)
    with client.stream(
        "POST",
        "/api/docs/ask",
        headers=headers,
        json={"query": "什么是好的友情", "top_k": 3},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = "".join(response.iter_text())

    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert types[0] == "stage" and events[0]["stage"] == "rewrite"
    assert "rewrite_delta" in types
    assert "rewrite_done" in types
    assert "retrieve_step" in types
    step_events = [e for e in events if e["type"] == "retrieve_step" and e.get("status") == "done"]
    steps = [e.get("step") for e in step_events]
    assert steps == ["vector", "keyword", "rrf", "rerank"]
    assert "retrieve_done" in types
    assert "answer_delta" in types
    assert "answer_done" in types
    assert types[-1] == "done" and events[-1]["ok"] is True

    rewrite_done = next(e for e in events if e["type"] == "rewrite_done")
    assert rewrite_done["original_query"] == "什么是好的友情"
    assert "优化:" in rewrite_done["optimized_query"]

    answer_done = next(e for e in events if e["type"] == "answer_done")
    assert "命中1条" in answer_done["answer"]

    db = db_session.SessionLocal()
    try:
        row = db.execute(select(AskLog).order_by(AskLog.id.desc())).scalars().first()
        assert row is not None
        assert row.status == "success"
        assert row.original_query == "什么是好的友情"
        assert row.optimized_query and "优化:" in row.optimized_query
        assert row.retrieve_total == 1
        assert row.answer and "命中1条" in row.answer
        assert row.model == settings.llm_model
    finally:
        db.close()


def test_ask_missing_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")

    class EmptyKeyClient(DeepSeekChatClient):
        def __init__(self) -> None:
            super().__init__(api_key="")

    monkeypatch.setattr("app.services.ask.get_llm_client", lambda: EmptyKeyClient())

    headers = _auth_headers(client)
    with client.stream(
        "POST",
        "/api/docs/ask",
        headers=headers,
        json={"query": "友情"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert types[0] == "error"
    assert events[0]["stage"] == "config"
    assert "LLM_API_KEY" in events[0]["message"]
    assert types[-1] == "done" and events[-1]["ok"] is False

    db = db_session.SessionLocal()
    try:
        row = db.execute(select(AskLog).order_by(AskLog.id.desc())).scalars().first()
        assert row is not None
        assert row.status == "error"
        assert row.error_stage == "config"
    finally:
        db.close()


def test_llm_not_configured_raises():
    client = DeepSeekChatClient(api_key="")
    try:
        client.ensure_configured()
        raise AssertionError("expected LLMNotConfiguredError")
    except LLMNotConfiguredError:
        pass


def test_ask_cancelled_stops_llm_and_logs(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "fake-key")
    fake = FakeLLM()
    monkeypatch.setattr("app.services.ask.get_llm_client", lambda: fake)
    monkeypatch.setattr("app.rag.ask_graph.rewrite_query_stream", _fake_rewrite_then_cancel)
    monkeypatch.setattr("app.rag.ask_graph.answer_from_hits_stream", _fake_answer)
    monkeypatch.setattr("app.rag.ask_graph.search_vector_hits", lambda **kwargs: [])
    monkeypatch.setattr("app.rag.ask_graph.search_keyword_hits", lambda **kwargs: [])

    headers = _auth_headers(client)
    with client.stream(
        "POST",
        "/api/docs/ask",
        headers=headers,
        json={"query": "中途取消测试"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = _parse_sse(body)
    types = [e["type"] for e in events]
    # 节点抛取消时 LangGraph 可能来不及刷出 rewrite_delta，以「未进入检索/回答」为准
    assert "answer_delta" not in types
    assert "retrieve_done" not in types
    assert types[-1] == "done"
    assert events[-1].get("cancelled") is True
    assert events[-1].get("ok") is False

    db = db_session.SessionLocal()
    try:
        row = db.execute(select(AskLog).order_by(AskLog.id.desc())).scalars().first()
        assert row is not None
        assert row.status == "cancelled"
        assert row.original_query == "中途取消测试"
    finally:
        db.close()
