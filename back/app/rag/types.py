from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedDocument:
    source_path: str
    title: str
    content: str
    content_hash: str
    updated_at: str | None = None
    file_mtime: datetime | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class TextChunk:
    chunk_index: int
    content: str
    content_hash: str
    char_start: int | None = None
    char_end: int | None = None
