from app.rag.indexer import DocumentIndexer
from app.core.config import settings


def _auth_headers(client) -> dict[str, str]:
    payload = {
        "username": "docsuser",
        "email": "docs@example.com",
        "password": "secret123",
    }
    client.post("/api/auth/register", json=payload)
    login = client.post(
        "/api/auth/login",
        json={"username": "docsuser", "password": "secret123"},
    )
    token = login.json()["data"]["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_document_requires_auth(client):
    response = client.post(
        "/api/docs/upload",
        files={"file": ("note.md", b"hello", "text/markdown")},
    )
    assert response.status_code == 401


def test_upload_document_saves_to_docs_dir(client, tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(settings, "rag_docs_dir", str(docs_dir))

    headers = _auth_headers(client)
    response = client.post(
        "/api/docs/upload",
        headers=headers,
        files={"file": ("团建笔记.md", "今天很好玩\n\n更新时间：2026年7月\n".encode("utf-8"), "text/markdown")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["filename"] == "团建笔记.md"
    assert body["data"]["path"] == "docs/团建笔记.md"
    assert (docs_dir / "团建笔记.md").exists()


def test_upload_rejects_unsupported_suffix(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "rag_docs_dir", str(tmp_path / "docs"))
    headers = _auth_headers(client)

    response = client.post(
        "/api/docs/upload",
        headers=headers,
        files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 400
    assert "仅支持" in response.json()["message"]


def test_index_documents(client, tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("hello\n\nworld\n", encoding="utf-8")
    monkeypatch.setattr(settings, "rag_docs_dir", str(docs_dir))

    def fake_index_all(self, docs_dir=None, rebuild: bool = False):
        return {"indexed": 1, "skipped": 0, "removed": 0, "chunks": 2}

    monkeypatch.setattr(DocumentIndexer, "index_all", fake_index_all)

    headers = _auth_headers(client)
    response = client.post("/api/docs/index", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"] == {"indexed": 1, "skipped": 0, "removed": 0, "chunks": 2}
    assert body["message"] == "知识库更新完成"
