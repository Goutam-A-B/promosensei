"""Test wiring: in-memory SQLite + scheduler off + fixtures on."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `import app.*` work regardless of the cwd pytest was launched from.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("SCRAPER_USE_FIXTURES", "true")

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.cache import reset_cache_for_tests  # noqa: E402
from app.db import Base  # noqa: E402
from app.observability import reset_metrics_for_tests  # noqa: E402
from app.resilience import reset_breakers_for_tests  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_phase4_singletons():
    """Phase 4 added a process-wide cache, metrics registry, and breaker
    map. Reset all three around every test so state from one case doesn't
    leak into the next (e.g. cached search response from an empty-index
    run masking a populated-index run with the same query)."""
    reset_cache_for_tests()
    reset_metrics_for_tests()
    reset_breakers_for_tests()
    yield
    reset_cache_for_tests()
    reset_metrics_for_tests()
    reset_breakers_for_tests()


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def fixtures_dir() -> Path:
    return BACKEND_ROOT / "fixtures" / "amazon"
