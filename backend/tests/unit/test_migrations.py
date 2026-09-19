"""schema.sql's CREATE TABLE IF NOT EXISTS only takes effect for a table
that does not exist yet, so revoked_at (CLAUDE.md 18.8) needs its own
guarded migration for a database created before that column existed.
These tests exercise that migration directly, separately from the
`conn` fixture (which already runs against the current, up-to-date
schema and so would never exercise the upgrade path).
"""

import sqlite3

from app.db import migrations


def _bare_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _legacy_source_locators(conn: sqlite3.Connection) -> None:
    """The source_locators shape before revoked_at was added."""
    conn.execute(
        """
        CREATE TABLE source_locators (
            document_id TEXT NOT NULL,
            source_locator TEXT NOT NULL,
            content_fingerprint TEXT NOT NULL,
            genesis_position INTEGER NOT NULL,
            first_seen_at TEXT NOT NULL,
            PRIMARY KEY (document_id, source_locator)
        )
        """
    )


def test_fresh_database_has_the_revoked_at_column():
    conn = _bare_connection()
    migrations.initialize(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(source_locators)")}
    assert "revoked_at" in columns


def test_legacy_table_without_revoked_at_is_upgraded():
    conn = _bare_connection()
    _legacy_source_locators(conn)
    conn.execute(
        "INSERT INTO source_locators VALUES (?, ?, ?, ?, ?)",
        ("doc1", "u0000", "abc123", 0, "2024-01-01T00:00:00+00:00"),
    )
    conn.commit()

    migrations.initialize(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(source_locators)")}
    assert "revoked_at" in columns


def test_existing_locator_rows_survive_the_migration_unchanged():
    conn = _bare_connection()
    _legacy_source_locators(conn)
    conn.execute(
        "INSERT INTO source_locators VALUES (?, ?, ?, ?, ?)",
        ("doc1", "u0000", "abc123", 0, "2024-01-01T00:00:00+00:00"),
    )
    conn.commit()

    migrations.initialize(conn)

    row = conn.execute(
        "SELECT * FROM source_locators WHERE document_id = ? AND source_locator = ?",
        ("doc1", "u0000"),
    ).fetchone()
    assert row["content_fingerprint"] == "abc123"
    assert row["genesis_position"] == 0
    assert row["first_seen_at"] == "2024-01-01T00:00:00+00:00"
    assert row["revoked_at"] is None


def test_initialize_is_idempotent_across_repeated_calls():
    conn = _bare_connection()
    migrations.initialize(conn)
    conn.execute(
        "INSERT INTO source_locators "
        "(document_id, source_locator, content_fingerprint, genesis_position, first_seen_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("doc1", "u0000", "abc123", 0, "2024-01-01T00:00:00+00:00"),
    )
    conn.commit()

    migrations.initialize(conn)
    migrations.initialize(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(source_locators)")}
    assert "revoked_at" in columns
    row = conn.execute(
        "SELECT * FROM source_locators WHERE document_id = ? AND source_locator = ?",
        ("doc1", "u0000"),
    ).fetchone()
    assert row is not None
    assert row["content_fingerprint"] == "abc123"


# ---------------------------- default row_factory (no sqlite3.Row set)


def test_fresh_database_initializes_with_default_tuple_row_factory():
    # No row_factory assignment at all -- the PRAGMA-column inspection
    # inside initialize() must not assume dict-style row access.
    conn = sqlite3.connect(":memory:")
    migrations.initialize(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(source_locators)")}
    assert "revoked_at" in columns


def test_legacy_table_upgrades_with_default_tuple_row_factory():
    conn = sqlite3.connect(":memory:")
    _legacy_source_locators(conn)
    conn.execute(
        "INSERT INTO source_locators VALUES (?, ?, ?, ?, ?)",
        ("doc1", "u0000", "abc123", 0, "2024-01-01T00:00:00+00:00"),
    )
    conn.commit()

    migrations.initialize(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(source_locators)")}
    assert "revoked_at" in columns

    row = conn.execute(
        "SELECT document_id, source_locator, content_fingerprint, genesis_position, "
        "first_seen_at, revoked_at FROM source_locators WHERE document_id = ? "
        "AND source_locator = ?",
        ("doc1", "u0000"),
    ).fetchone()
    assert row == ("doc1", "u0000", "abc123", 0, "2024-01-01T00:00:00+00:00", None)


def test_initialize_is_idempotent_with_default_tuple_row_factory():
    conn = sqlite3.connect(":memory:")
    migrations.initialize(conn)
    migrations.initialize(conn)
    migrations.initialize(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(source_locators)")}
    assert "revoked_at" in columns
