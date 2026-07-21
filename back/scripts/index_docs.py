#!/usr/bin/env python3
"""Index local markdown documents into SQLite and ChromaDB."""

import argparse
import sys
from pathlib import Path

# 保证从 scripts/ 运行时也能 import app.*
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db.session import SessionLocal, engine, ensure_data_dir
from app.models import document, document_chunk  # noqa: F401
from app.rag.indexer import DocumentIndexer


def main() -> None:
    parser = argparse.ArgumentParser(description="Index local docs for RAG")
    parser.add_argument("--rebuild", action="store_true", help="Clear and rebuild all indexes")
    args = parser.parse_args()

    ensure_data_dir()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        stats = DocumentIndexer(db).index_all(rebuild=args.rebuild)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(
        "Index finished: "
        f"indexed={stats['indexed']}, "
        f"skipped={stats['skipped']}, "
        f"removed={stats['removed']}, "
        f"chunks={stats['chunks']}"
    )


if __name__ == "__main__":
    main()
