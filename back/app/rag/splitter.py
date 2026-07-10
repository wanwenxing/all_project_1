import hashlib

from app.core.config import settings
from app.rag.types import ParsedDocument, TextChunk

MIN_PARAGRAPH_SIZE = 50


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


def _split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    pieces: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        pieces.append(text[start:end].strip())
        if end >= text_length:
            break
        start = max(end - overlap, 0)

    return [piece for piece in pieces if piece]
