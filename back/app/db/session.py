from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def ensure_data_dir() -> None:
    if settings.database_url.startswith("sqlite:///./"):
        db_path = settings.database_url.removeprefix("sqlite:///./")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
ensure_data_dir()
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
