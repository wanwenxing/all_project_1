import hashlib
import re

from app.core.config import settings
from app.rag.types import ParsedDocument, TextChunk

MIN_PARAGRAPH_SIZE = 50
# 优先在这些标点后切开，尽量保持句子完整
SENTENCE_END_PATTERN = re.compile(r"[。！？；.!?;]")


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def split_document(document: ParsedDocument) -> list[TextChunk]:
    paragraphs = [part.strip() for part in document.content.split("\n\n") if part.strip()]
    merged = _merge_short_paragraphs(paragraphs)

    chunks: list[TextChunk] = []
    chunk_index = 0
    cursor = 0

    for paragraph in merged:
        start = document.content.find(paragraph, cursor)
        if start < 0:
            start = cursor
        end = start + len(paragraph)
        cursor = end

        for piece in _split_long_text(paragraph, settings.rag_chunk_size, settings.rag_chunk_overlap):
            piece_start = document.content.find(piece, start)
            piece_end = piece_start + len(piece) if piece_start >= 0 else None
            chunks.append(
                TextChunk(
                    chunk_index=chunk_index,
                    content=piece,
                    content_hash=_content_hash(piece),
                    char_start=piece_start if piece_start >= 0 else start,
                    char_end=piece_end,
                )
            )
            chunk_index += 1

    return chunks


def _merge_short_paragraphs(paragraphs: list[str]) -> list[str]:
    if not paragraphs:
        return []

    merged: list[str] = []
    buffer = paragraphs[0]

    for paragraph in paragraphs[1:]:
        if len(buffer) < MIN_PARAGRAPH_SIZE:
            buffer = f"{buffer}\n\n{paragraph}"
        else:
            merged.append(buffer)
            buffer = paragraph

    merged.append(buffer)
    return merged


def _find_punctuation_cut(text: str, start: int, ideal_end: int) -> int | None:
    """在 [start, ideal_end) 窗口后半段内，从后往前找最近的句子标点，返回切点（标点后）。"""
    if ideal_end <= start:
        return None

    # 避免切出过短块：只在窗口后半段寻找标点
    window_start = start + max((ideal_end - start) // 2, 1)
    region = text[window_start:ideal_end]
    matches = list(SENTENCE_END_PATTERN.finditer(region))
    if not matches:
        return None
    last = matches[-1]
    return window_start + last.end()


def _split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    pieces: list[str] = []
    start = 0
    text_length = len(text)
    overlap = max(0, min(overlap, chunk_size - 1))

    while start < text_length:
        ideal_end = min(start + chunk_size, text_length)
        if ideal_end >= text_length:
            piece = text[start:].strip()
            if piece:
                pieces.append(piece)
            break

        cut = _find_punctuation_cut(text, start, ideal_end)
        end = cut if cut is not None else ideal_end

        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)

        next_start = max(end - overlap, start + 1)
        if next_start <= start:
            next_start = end
        start = next_start

    return [piece for piece in pieces if piece]
