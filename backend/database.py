import os
import shutil
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_HERE = Path(__file__).resolve().parent


def _resolve_database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured

    # Vercel's deployment bundle is read-only at runtime. Copy the tracked
    # SQLite snapshot into /tmp on cold start so the API can still cache CARFAX
    # lookups and run lightweight migrations inside the function sandbox.
    if os.getenv("VERCEL"):
        source_db = _HERE / "alm.db"
        tmp_db = Path("/tmp/alm.db")
        if source_db.exists() and not tmp_db.exists():
            shutil.copy2(source_db, tmp_db)
        return f"sqlite:///{tmp_db}"

    return "sqlite:///./alm.db"


SQLALCHEMY_DATABASE_URL = _resolve_database_url()

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
