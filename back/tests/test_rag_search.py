from app.core.config import settings
from app.rag.chroma_store import ChromaStore
from app.rag.fts_store import FTSStore
from app.rag.hybrid import rrf_fuse
from app.rag.indexer import DocumentIndexer
from app.rag.tokenize import build_fts_query, tokenize_for_fts
from app.services.docs import search_knowledge_base


class FakeEmbedder:
    model_name = "fake-bge"
    dimension = 1024

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] + [0.0] * 1021 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3] + [0.0] * 1021


class FakeReranker:
    def rerank(self, query: str, hits: list[dict], *, top_k: int) -> list[dict]:
        # 保序截断，便于断言混合结果已进入精排
        result = []
        for hit in hits[:top_k]:
            item = dict(hit)
            item["rerank_score"] = 0.9
            item["score"] = 0.9
            result.append(item)
        return result


def test_tokenize_and_fts_query():
    tokenized = tokenize_for_fts("今天小彭分享了一段视频")
    assert "小彭" in tokenized
    assert " " in tokenized
    fts_query = build_fts_query("小彭的视频")
    assert fts_query is not None
    assert "小彭" in fts_query


def test_rrf_fuse_prefers_overlap():
    vector = [
        {"chunk_id": "1", "content": "a", "score": 0.8},
        {"chunk_id": "2", "content": "b", "score": 0.7},
    ]
    keyword = [
        {"chunk_id": "2", "content": "b", "bm25_score": -3.0},
        {"chunk_id": "3", "content": "c", "bm25_score": -2.0},
    ]
    merged = rrf_fuse(vector, keyword, k=60, limit=3)
    assert merged[0]["chunk_id"] == "2"


def test_hybrid_search_returns_top_k(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    chroma_dir = tmp_path / "chroma"
    (docs_dir / "友情.md").write_text(
        "长久的友情甚至更胜于一般的爱情。小彭今天分享了一段视频。\n\n更新时间：2026年6月\n",
        encoding="utf-8",
    )
    (docs_dir / "团建.md").write_text(
        "今天去吃烤肉，团建很有意思。\n\n更新时间：2026年7月\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "rag_docs_dir", str(docs_dir))
    monkeypatch.setattr(settings, "rag_chroma_dir", str(chroma_dir))
    monkeypatch.setattr(settings, "rag_hybrid_enabled", True)
    monkeypatch.setattr(settings, "rag_rerank_enabled", True)
    monkeypatch.setattr(settings, "rag_fetch_k", 5)
    monkeypatch.setattr(settings, "rag_candidate_k", 5)
    monkeypatch.setattr(settings, "rag_default_top_k", 2)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.base import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'search.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    chroma = ChromaStore()
    indexer = DocumentIndexer(session, chroma_store=chroma, embedder=FakeEmbedder())
    indexer.index_file(docs_dir / "友情.md")
    indexer.index_file(docs_dir / "团建.md")
    session.commit()

    # FTS 应已写入
    fts_count = session.execute(
        __import__("sqlalchemy").text("SELECT COUNT(*) FROM chunk_fts")
    ).scalar()
    assert fts_count >= 1

    keyword_hits = FTSStore(session).search("小彭", limit=5)
    assert any("小彭" in (hit["content"] or "") for hit in keyword_hits)

    monkeypatch.setattr("app.services.docs.get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("app.services.docs.get_chroma_store", lambda: chroma)
    monkeypatch.setattr("app.services.docs.get_reranker", lambda: FakeReranker())
    monkeypatch.setattr("app.services.docs.SessionLocal", sessionmaker(bind=engine))

    result = search_knowledge_base(query="小彭分享的视频", top_k=2)
    assert result["total"] <= 2
    assert len(result["hits"]) <= 2
    assert result["total"] >= 1

    session.close()


def test_search_vector_and_source_path_filter(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    chroma_dir = tmp_path / "chroma"
    (docs_dir / "友情.md").write_text(
        "长久的友情甚至更胜于一般的爱情。\n\n更新时间：2026年6月\n",
        encoding="utf-8",
    )
    (docs_dir / "团建.md").write_text(
        "今天去吃烤肉，团建很有意思。\n\n更新时间：2026年7月\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "rag_docs_dir", str(docs_dir))
    monkeypatch.setattr(settings, "rag_chroma_dir", str(chroma_dir))
    monkeypatch.setattr(settings, "rag_hybrid_enabled", True)
    monkeypatch.setattr(settings, "rag_rerank_enabled", True)
    monkeypatch.setattr(settings, "rag_fetch_k", 5)
    monkeypatch.setattr(settings, "rag_candidate_k", 5)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.base import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'search.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    chroma = ChromaStore()
    indexer = DocumentIndexer(session, chroma_store=chroma, embedder=FakeEmbedder())
    indexer.index_file(docs_dir / "友情.md")
    indexer.index_file(docs_dir / "团建.md")
    session.commit()

    monkeypatch.setattr("app.services.docs.get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("app.services.docs.get_chroma_store", lambda: chroma)
    monkeypatch.setattr("app.services.docs.get_reranker", lambda: FakeReranker())
    monkeypatch.setattr("app.services.docs.SessionLocal", sessionmaker(bind=engine))

    all_hits = search_knowledge_base(query="友情", top_k=5)
    assert all_hits["total"] >= 1
    assert any(hit["source_path"] == "docs/友情.md" for hit in all_hits["hits"])

    filtered = search_knowledge_base(
        query="团建",
        top_k=5,
        source_path="docs/友情.md",
    )
    assert all(hit["source_path"] == "docs/友情.md" for hit in filtered["hits"])

    by_title = search_knowledge_base(query="爱情", top_k=5, title="友情")
    assert by_title["total"] >= 1
    assert all(hit["title"] == "友情" for hit in by_title["hits"])

    session.close()


def test_search_filters_hits_below_min_score(monkeypatch):
    monkeypatch.setattr(settings, "rag_min_score", 0.5)
    monkeypatch.setattr(settings, "rag_hybrid_enabled", False)
    monkeypatch.setattr(settings, "rag_rerank_enabled", False)

    class StubStore:
        def query(self, query_embedding, *, n_results=5, where=None):
            return [
                {
                    "chroma_id": "chunk:1",
                    "content": "高相关内容",
                    "distance": 0.2,
                    "score": 0.8,
                    "metadata": {"source_path": "docs/a.md", "title": "a", "chunk_id": "1"},
                },
                {
                    "chroma_id": "chunk:2",
                    "content": "低相关内容",
                    "distance": 0.7,
                    "score": 0.3,
                    "metadata": {"source_path": "docs/b.md", "title": "b", "chunk_id": "2"},
                },
            ]

    monkeypatch.setattr("app.services.docs.get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("app.services.docs.get_chroma_store", lambda: StubStore())

    result = search_knowledge_base(query="测试", top_k=5)
    assert result["total"] == 1
    assert result["hits"][0]["chroma_id"] == "chunk:1"
    assert result["hits"][0]["score"] == 0.8
