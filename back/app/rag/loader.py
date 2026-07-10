import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.rag.types import ParsedDocument

FRONT_MATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
UPDATED_LABEL_PATTERN = re.compile(r"更新时间[：:]\s*(.+?)\s*$", re.MULTILINE)
SUPPORTED_SUFFIXES = {".md", ".txt"}


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = FRONT_MATTER_PATTERN.match(text)
    if not match:
        return {}, text

    raw_meta = yaml.safe_load(match.group(1)) or {}
    metadata = {key: str(value) for key, value in raw_meta.items()}
    return metadata, text[match.end() :]


def _extract_updated_label(content: str) -> tuple[str, str | None]:
    match = UPDATED_LABEL_PATTERN.search(content)
    if not match:
        return content, None

    updated_label = match.group(1).strip()
    cleaned = UPDATED_LABEL_PATTERN.sub("", content).strip()
    return cleaned, updated_label


def _title_from_path(path: Path) -> str:
    return path.stem


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _resolve_updated_at(
    front_matter: dict[str, str],
    updated_label: str | None,
    file_mtime: datetime | None,
) -> str | None:
    for key in ("updated_at", "date"):
        if key in front_matter and front_matter[key]:
            return front_matter[key]
    if updated_label:
        return updated_label
    if file_mtime is not None:
        return file_mtime.astimezone(UTC).date().isoformat()
    return None


def load_documents(docs_dir: str | Path) -> list[ParsedDocument]:
    root = Path(docs_dir).resolve()
    if not root.exists():
        return []

    documents: list[ParsedDocument] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue

        raw_text = file_path.read_text(encoding="utf-8")
        front_matter, body = _parse_front_matter(raw_text)
        body, updated_label = _extract_updated_label(body)
        body = body.strip()

        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)
        relative_path = file_path.relative_to(root.parent).as_posix()
        title = str(front_matter.get("title") or _title_from_path(file_path))

        documents.append(
            ParsedDocument(
                source_path=relative_path,
                title=title,
                content=body,
                content_hash=_content_hash(body),
                updated_at=_resolve_updated_at(front_matter, updated_label, file_mtime),
                file_mtime=file_mtime,
                metadata={
                    key: str(value)
                    for key, value in front_matter.items()
                    if key not in {"title", "updated_at", "date"}
                },
            )
        )

    return documents
