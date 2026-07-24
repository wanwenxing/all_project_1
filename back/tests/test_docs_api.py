from app.core.config import settings
from app.rag.indexer import DocumentIndexer


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
        files={
            "file": (
                "团建笔记.md",
                "今天很好玩\n\n更新时间：2026年7月\n".encode("utf-8"),
                "text/markdown",
            )
        },
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


def test_index_single_file_by_path(client, tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "only.md").write_text("单文件内容\n", encoding="utf-8")
    (docs_dir / "other.md").write_text("不应被扫描\n", encoding="utf-8")
    monkeypatch.setattr(settings, "rag_docs_dir", str(docs_dir))

    calls: list[str] = []

    def fake_index_file(self, file_path, *, force: bool = False):
        calls.append(str(file_path))
        return {"indexed": 1, "skipped": 0, "removed": 0, "chunks": 1}

    monkeypatch.setattr(DocumentIndexer, "index_file", fake_index_file)

    headers = _auth_headers(client)
    response = client.post(
        "/api/docs/index",
        headers=headers,
        params={"path": "docs/only.md"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "单文件知识库更新完成"
    assert body["data"]["indexed"] == 1
    assert len(calls) == 1
    assert calls[0].endswith("only.md")
