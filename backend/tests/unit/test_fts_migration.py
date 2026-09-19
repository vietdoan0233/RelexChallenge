import json
import sqlite3

from app.db import migrations


def test_old_fts_shape_is_upgraded_without_touching_embeddings(seed_units):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrations.initialize(conn)
    ids = seed_units(conn, "doc", [("hello bakery", "Ana", "2025-01-01")], title="Kickoff")
    conn.execute(
        "INSERT INTO evidence_embeddings VALUES (?, 'm', ?)", (ids[0], json.dumps([1.0, 0.0]))
    )
    # Recreate the pre-upgrade single-column FTS table.
    conn.execute("DROP TABLE evidence_fts")
    conn.execute("CREATE VIRTUAL TABLE evidence_fts USING fts5(evidence_id UNINDEXED, raw_text)")
    conn.execute("INSERT INTO evidence_fts VALUES (?, 'hello bakery')", (ids[0],))
    conn.commit()

    migrations.initialize(conn)

    columns = [r[1] for r in conn.execute("PRAGMA table_info(evidence_fts)")]
    assert columns == ["evidence_id", "raw_text", "thread_context", "speaker_sender"]
    row = conn.execute(
        "SELECT evidence_id FROM evidence_fts WHERE evidence_fts MATCH 'Kickoff'"
    ).fetchone()
    assert row["evidence_id"] == ids[0]
    assert conn.execute("SELECT COUNT(*) FROM evidence_embeddings").fetchone()[0] == 1


def test_initialize_is_idempotent_on_the_current_shape(conn):
    migrations.initialize(conn)
    migrations.initialize(conn)
    assert len(list(conn.execute("PRAGMA table_info(evidence_fts)"))) == 4
