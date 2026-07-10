#!/usr/bin/env python3
"""Index local markdown documents into SQLite and ChromaDB."""

import argparse

from app.db.session import SessionLocal
from app.rag.indexer import DocumentIndexer


def main() -> None:
    parser = argparse.ArgumentParser(description="Index local docs for RAG")
    parser.add_argument("--rebuild", action="store_true", help="Clear and rebuild all indexes")
    args = parser.parse_args()

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
