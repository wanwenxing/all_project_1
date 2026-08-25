"""Agent API 单测：mock 图运行，不打真实 LLM。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _auth_headers(client) -> dict[str, str]:
    payload = {
        "username": "agentuser",
        "email": "agent@example.com",
        "password": "secret123",
    }
    client.post("/api/auth/register", json=payload)
    login = client.post(
        "/api/auth/login",
        json={"username": "agentuser", "password": "secret123"},
    )
    token = login.json()["data"]["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_agent_run_requires_auth(client):
    resp = client.post("/api/agent", json={"message": "3*5+1"})
    assert resp.status_code == 401


def test_agent_run_ok(client, monkeypatch):
    graph = MagicMock()
    graph.ainvoke = AsyncMock(
        return_value={
            "messages": [
                HumanMessage(content="3*5+1等于多少"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "multiply",
                            "args": {"a": 3, "b": 5},
                            "id": "t1",
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(content="15.0", tool_call_id="t1", name="multiply"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "add",
                            "args": {"a": 15, "b": 1},
                            "id": "t2",
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(content="16.0", tool_call_id="t2", name="add"),
                AIMessage(content="答案是 16"),
            ]
        }
    )
    monkeypatch.setattr(
        "app.services.agent.get_compiled_agent_graph",
        AsyncMock(return_value=graph),
    )

    headers = _auth_headers(client)
    resp = client.post("/api/agent", json={"message": "3*5+1等于多少"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["answer"] == "答案是 16"
    assert [s["name"] for s in body["data"]["tool_steps"]] == ["multiply", "add"]
    graph.ainvoke.assert_awaited()
