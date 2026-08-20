"""记忆对话会话 API（不依赖真实 LLM / embedding）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.memory_chat import reset_memory_chat_for_tests


def _register_and_login(client: TestClient, suffix: str) -> str:
    username = f"mem_{suffix}"
    email = f"mem_{suffix}@example.com"
    password = "Passw0rd!"
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    token = resp.json()["data"]["token"]["access_token"]
    return token


def test_chat_session_crud():
    reset_memory_chat_for_tests()
    client = TestClient(app)
    token = _register_and_login(client, "s1")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/chat/sessions", json={"title": "测试窗"}, headers=headers)
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["title"] == "测试窗"
    thread_id = data["thread_id"]

    listed = client.get("/api/chat/sessions", headers=headers)
    assert listed.status_code == 200
    assert any(s["thread_id"] == thread_id for s in listed.json()["data"])

    deleted = client.delete(f"/api/chat/sessions/{thread_id}", headers=headers)
    assert deleted.status_code == 200
    listed2 = client.get("/api/chat/sessions", headers=headers)
    assert all(s["thread_id"] != thread_id for s in listed2.json()["data"])
