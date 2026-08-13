from app.llm.ask_llm import (
    ANSWER_HEADER,
    EVIDENCE_HEADER,
    ensure_answer_with_evidence,
    format_evidence_block,
    public_sources,
)


def test_ensure_answer_appends_evidence_when_missing():
    hits = [
        {
            "title": "友情",
            "source_path": "docs/友情.md",
            "content": "友情胜过一般的爱情",
            "score": 0.9,
        }
    ]
    out = ensure_answer_with_evidence("这是答案正文", hits)
    assert out.startswith(ANSWER_HEADER)
    assert EVIDENCE_HEADER in out
    assert "友情胜过一般的爱情" in out
    assert "docs/友情.md" in out


def test_ensure_answer_keeps_model_evidence_block():
    raw = f"{ANSWER_HEADER}\n答法\n\n{EVIDENCE_HEADER}\n[1] 标题=x 路径=y；摘录：z"
    out = ensure_answer_with_evidence(raw, [])
    assert out == raw


def test_public_sources_shape():
    sources = public_sources(
        [{"title": "t", "source_path": "p", "content": "c", "score": 0.5, "chroma_id": "1"}]
    )
    assert sources == [
        {
            "index": 1,
            "title": "t",
            "source_path": "p",
            "content": "c",
            "score": 0.5,
            "chroma_id": "1",
            "document_id": None,
            "chunk_id": None,
            "chunk_index": None,
        }
    ]


def test_format_evidence_block_empty():
    assert "无命中材料" in format_evidence_block([])
