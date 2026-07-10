import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.rag.chroma_store import ChromaStore
from app.rag.indexer import DocumentIndexer
from app.rag.loader import load_documents
from app.rag.splitter import split_document


class FakeEmbedder:
    model_name = "fake-bge"
    dimension = 1024

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] + [0.0] * 1021 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3] + [0.0] * 1021


@pytest.fixture
def rag_session(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    chroma_dir = tmp_path / "chroma"
    db_path = tmp_path / "test.db"

    sample = docs_dir / "sample.md"
    sample.write_text(
        "今天去吃烤肉，和同事聊了很多关于工作的想法，感觉收获挺大的。\n\n"
        "听了前辈讲职业迷茫和收支规划，觉得世界就是变化的，人之间的交往本质都是等价互换。\n\n"
        "更新时间：2026年6月\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "rag_docs_dir", str(docs_dir))
    monkeypatch.setattr(settings, "rag_chroma_dir", str(chroma_dir))

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_load_documents_extracts_metadata(rag_session):
    documents = load_documents(settings.rag_docs_dir)
    assert len(documents) == 1
    document = documents[0]
    assert document.title == "sample"
    assert "烤肉" in document.content
    assert document.updated_at == "2026年6月"
    assert document.content_hash


def test_split_document_by_paragraphs(rag_session):
    document = load_documents(settings.rag_docs_dir)[0]
    chunks = split_document(document)
    assert len(chunks) >= 1
    merged_content = "\n".join(chunk.content for chunk in chunks)
    assert "烤肉" in merged_content
    assert "职业迷茫" in merged_content


def test_split_document_creates_multiple_chunks_for_long_text(rag_session, tmp_path, monkeypatch):
    docs_dir = tmp_path / "long_docs"
    docs_dir.mkdir()
    long_doc = docs_dir / "long.md"
    long_doc.write_text(
        ("这是一段很长的日记内容，" * 20 + "\n\n") * 3,
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "rag_docs_dir", str(docs_dir))

    document = load_documents(settings.rag_docs_dir)[0]
    chunks = split_document(document)
    assert len(chunks) >= 2


def test_index_writes_sql_and_chroma(rag_session):
    indexer = DocumentIndexer(
        rag_session,
        chroma_store=ChromaStore(),
        embedder=FakeEmbedder(),
    )

    stats = indexer.index_all()
    rag_session.commit()

    assert stats["indexed"] == 1
    assert stats["chunks"] >= 1

    document = rag_session.scalar(select(Document))
    assert document is not None
    assert document.index_status == "indexed"
    assert document.embedding_model == "fake-bge"
    assert document.chunk_count >= 1

    chunks = rag_session.scalars(select(DocumentChunk)).all()
    assert len(chunks) == document.chunk_count
    assert all(chunk.chroma_id.startswith("chunk:") for chunk in chunks)

    chroma = ChromaStore()
    assert chroma.count() == document.chunk_count


def test_index_skips_unchanged_document(rag_session):
    indexer = DocumentIndexer(
        rag_session,
        chroma_store=ChromaStore(),
        embedder=FakeEmbedder(),
    )

    first = indexer.index_all()
    rag_session.commit()
    second = indexer.index_all()
    rag_session.commit()

    assert first["indexed"] == 1
    assert second["skipped"] == 1
    assert second["indexed"] == 0
