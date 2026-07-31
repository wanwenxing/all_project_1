import json

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
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


async def _fake_rewrite(_llm, original: str):
    for part in ["优化:", original[:8]]:
        yield part


async def _fake_answer(_llm, *, original_query, optimized_query, hits):
    yield "根据材料："
    yield f"命中{len(hits)}条。"


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
        "app.rag.ask_graph.search_knowledge_base",
        lambda **kwargs: {
            "query": kwargs["query"],
            "total": 1,
            "hits": [
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
        },
    )

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
    assert "retrieve_done" in types
    assert "answer_delta" in types
    assert "answer_done" in types
    assert types[-1] == "done" and events[-1]["ok"] is True

    rewrite_done = next(e for e in events if e["type"] == "rewrite_done")
    assert rewrite_done["original_query"] == "什么是好的友情"
    assert "优化:" in rewrite_done["optimized_query"]

    answer_done = next(e for e in events if e["type"] == "answer_done")
    assert "命中1条" in answer_done["answer"]

    db = SessionLocal()
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

    db = SessionLocal()
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
