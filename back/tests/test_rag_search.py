from app.core.config import settings
from app.rag.chroma_store import ChromaStore
from app.rag.indexer import DocumentIndexer
from app.services.docs import search_knowledge_base


class FakeEmbedder:
    model_name = "fake-bge"
    dimension = 1024

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] + [0.0] * 1021 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3] + [0.0] * 1021


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

    all_hits = search_knowledge_base(query="友情", top_k=5)
    assert all_hits["total"] >= 1
    assert any(hit["source_path"] == "docs/友情.md" for hit in all_hits["hits"])

    filtered = search_knowledge_base(
        query="团建",
        top_k=5,
        source_path="docs/友情.md",
    )
    # 条件限制在友情文件后，不应再返回团建文件
    assert all(hit["source_path"] == "docs/友情.md" for hit in filtered["hits"])

    by_title = search_knowledge_base(query="爱情", top_k=5, title="友情")
    assert by_title["total"] >= 1
    assert all(hit["title"] == "友情" for hit in by_title["hits"])

    session.close()
