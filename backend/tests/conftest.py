import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.db import migrations


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    migrations.initialize(connection)
    yield connection
    connection.close()


@dataclass
class IsolatedInstance:
    """A temporary, on-disk instance -- source dir, database, artifacts
    dir, cache dir -- for tests that need real on-disk behavior (WAL/
    VACUUM purge tests) rather than the in-memory `conn` fixture used for
    pure logic tests. See CLAUDE.md/AGENTS.md section 0.5: any test that
    modifies source content, deletes a person, or simulates purge/rebuild
    must use an instance shaped like this one and must never touch the
    repository's own data/source/, data/app.db, or data/keeper.db."""

    source_dir: Path
    db_path: Path
    artifacts_dir: Path
    cache_dir: Path
    conn: sqlite3.Connection


@pytest.fixture
def isolated_instance(tmp_path):
    source_dir = tmp_path / "source"
    artifacts_dir = tmp_path / "artifacts"
    cache_dir = tmp_path / "cache"
    source_dir.mkdir()
    artifacts_dir.mkdir()
    cache_dir.mkdir()

    db_path = tmp_path / "app.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    migrations.initialize(connection)

    yield IsolatedInstance(
        source_dir=source_dir,
        db_path=db_path,
        artifacts_dir=artifacts_dir,
        cache_dir=cache_dir,
        conn=connection,
    )
    connection.close()
