from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.rag.fts_store import CREATE_FTS_SQL, FTSStore
from app.db.session import SessionLocal


def run_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "token_version" not in columns:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")
            )

    # FTS5 关键字索引：建表；若业务 chunk 有数据而 FTS 为空则回填
    with engine.begin() as conn:
        conn.execute(text(CREATE_FTS_SQL))

    if inspector.has_table("document_chunks"):
        db = SessionLocal()
        try:
            fts = FTSStore(db)
            fts.ensure_schema()
            chunk_count = db.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar() or 0
            fts_count = db.execute(text("SELECT COUNT(*) FROM chunk_fts")).scalar() or 0
            if chunk_count > 0 and fts_count == 0:
                fts.backfill_from_chunks()
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
