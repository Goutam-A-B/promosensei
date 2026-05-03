from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

def _engine_kwargs(url: str) -> dict:
    # SQLite (used in tests) does not accept QueuePool sizing kwargs.
    if url.startswith("sqlite"):
        return {"future": True}
    return {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "future": True,
    }


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
