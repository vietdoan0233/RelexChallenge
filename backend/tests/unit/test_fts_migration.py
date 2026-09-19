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


def test_search_text_drops_the_mail_banner_but_never_changes_raw_text():
    from app.ingestion.text_utils import search_text

    banner = (
        "This email originated from outside of RELEX. Be careful of attachments and links from "
        "unknown senders. Report suspicious emails using the report button."
    )
    raw = f"{banner}\n\nSigned and attached. [Image removed by sender]"
    assert search_text(raw) == "Signed and attached."
    assert "originated" in raw  # the stored/cited text is untouched


def test_a_stale_fts_version_is_rebuilt_in_place_without_touching_embeddings(conn, seed_units):
    import json

    from app.db import migrations

    banner = (
        "This email originated from outside of RELEX. Be careful of attachments and links from "
        "unknown senders. Report suspicious emails using the report button."
    )
    ids = seed_units(conn, "d", [f"{banner} Signed and attached."], title="Signoff")
    conn.execute("INSERT INTO evidence_embeddings VALUES (?, 'm', ?)", (ids[0], json.dumps([1.0])))
    conn.execute("DELETE FROM derived_meta")  # pretend the index predates the version stamp
    conn.commit()
    assert "originated" in conn.execute("SELECT raw_text FROM evidence_fts").fetchone()[0]

    migrations.initialize(conn)

    assert "originated" not in conn.execute("SELECT raw_text FROM evidence_fts").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM evidence_embeddings").fetchone()[0] == 1
    assert conn.execute("SELECT value FROM derived_meta").fetchone()[0] == migrations.FTS_VERSION
