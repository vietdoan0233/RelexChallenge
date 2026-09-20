import sqlite3

from app.db.connection import apply_schema

# Tables ingestion fully regenerates from data/source/ on every run.
# Dropping them before re-ingesting is what makes rebuild idempotent
# instead of accumulating duplicates. people/person_aliases are
# deliberately NOT in this list (Architecture v1.6, CLAUDE.md 18.0): a
# subject's subject_id and display_alias must survive a rebuild, so
# identity is now persistent state that ingestion matches against and
# updates in place (app/ingestion/people.py), not a name-derived value
# recomputed fresh every run. evidence_people stays rebuildable: it is a
# pure join of the now-stable subject_id against the already-stable
# evidence_id, so recomputing it every run is still safe.
_REBUILDABLE_TABLES = [
    "evidence_fts",
    "evidence_embeddings",
    "evidence_people",
    "evidence_units",
    "documents",
]


def initialize(conn: sqlite3.Connection) -> None:
    _ensure_fts_indexes_context(conn)
    _ensure_subject_identity_schema(conn)
    apply_schema(conn)
    _ensure_source_locators_revoked_at_column(conn)
    # An index built before the indexed text changed is rebuilt from the units.
    if conn.execute("SELECT 1 FROM evidence_units LIMIT 1").fetchone() and not _fts_is_current(
        conn
    ):
        _rebuild_fts_from_units(conn)


# Bump when what FTS indexes changes (columns or the text fed to it). 2: gateway
# boilerplate stripped from the indexed text.
FTS_VERSION = "2"


def _fts_is_current(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM derived_meta WHERE key = 'fts_version'").fetchone()
    return row is not None and row[0] == FTS_VERSION


def mark_fts_current(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO derived_meta (key, value) VALUES ('fts_version', ?)", (FTS_VERSION,)
    )
    conn.commit()


def _rebuild_fts_from_units(conn: sqlite3.Connection) -> None:
    """Repopulate the derived index from evidence_units. Embeddings and every
    other table are untouched, so no provider call is needed."""
    from app.ingestion.text_utils import search_text

    conn.execute("DELETE FROM evidence_fts")
    rows = conn.execute(
        "SELECT evidence_id, raw_text, COALESCE(thread_context, ''), COALESCE(speaker_sender, '') "
        "FROM evidence_units"
    ).fetchall()
    conn.executemany(
        "INSERT INTO evidence_fts (evidence_id, raw_text, thread_context, speaker_sender) "
        "VALUES (?, ?, ?, ?)",
        [(r[0], search_text(r[1]), r[2], r[3]) for r in rows],
    )
    mark_fts_current(conn)


def _ensure_fts_indexes_context(conn: sqlite3.Connection) -> None:
    """Upgrade an FTS table created before thread_context/speaker_sender
    were indexed. FTS5 cannot ALTER a column in, so the derived index is
    dropped, recreated from schema.sql, and repopulated from
    evidence_units. Only evidence_fts is touched: embeddings and every
    other table are left exactly as they were, so no provider call is
    needed. Positional PRAGMA access, as below, for row-factory safety."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(evidence_fts)")}
    if not columns or "thread_context" in columns:
        return
    conn.execute("DROP TABLE evidence_fts")
    apply_schema(conn)
    _rebuild_fts_from_units(conn)
    conn.commit()


def _ensure_source_locators_revoked_at_column(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS in schema.sql only takes effect for a
    table that does not exist yet, so a database created before
    revoked_at was added to source_locators needs this explicit, guarded
    upgrade -- schema.sql alone cannot add a column to an
    already-existing table. Never drops or recreates source_locators
    (see its persistence invariant in schema.sql's header comment); the
    PRAGMA check makes this safe to call on every startup/ingest,
    including a database that already has the column, whether because it
    was created fresh from the current schema.sql or already upgraded by
    a prior call.

    Column access is positional (row[1], PRAGMA table_info's documented
    "name" position), not row["name"] -- this function must work on a
    plain sqlite3.Connection whose row_factory was never set to
    sqlite3.Row, e.g. a connection built by code that hasn't opted into
    dict-style rows yet. row["name"] would raise TypeError against a
    connection left at the default tuple row factory."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(source_locators)")}
    if "revoked_at" not in columns:
        conn.execute("ALTER TABLE source_locators ADD COLUMN revoked_at TEXT")
    if "starts_group" not in columns:
        conn.execute("ALTER TABLE source_locators ADD COLUMN starts_group INTEGER")
    conn.commit()


def _ensure_subject_identity_schema(conn: sqlite3.Connection) -> None:
    """One-time migration off the retired v1.5 name-derived identity schema
    (people.person_id/canonical_name) onto the v1.6 subject model
    (people.subject_id/display_alias -- CLAUDE.md 18.0). `CREATE TABLE IF
    NOT EXISTS` cannot change an existing table's columns, so a database
    created before this migration needs an explicit, guarded reset.

    people/person_aliases/evidence_people are safe to drop here even though
    they are otherwise persistent (see _REBUILDABLE_TABLES's comment)
    specifically because there is no reversible translation from a
    name-derived person_id to a random subject_id -- carrying old rows
    forward would either fabricate a subject_id from the very name-derived
    material v1.6 exists to eliminate, or leave a mixed schema where some
    records use the old identity and some the new one, which AGENTS.md/
    CLAUDE.md 18.0 explicitly rules out. Every one of these rows is, by the
    same rebuildable-identity contract that used to reset them every
    ingest, fully re-derivable from data/source/ plus the reviewed identity
    manifest: the next ingestion run repopulates them under fresh, random
    subject_ids, and every ingest after that preserves those.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(people)")}
    if not columns or "subject_id" in columns:
        return
    conn.commit()  # PRAGMA foreign_keys is a no-op inside a transaction
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for table in ("evidence_people", "person_aliases", "people"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def reset_rebuildable_tables(conn: sqlite3.Connection) -> None:
    """Drop and recreate exactly the ingestion-owned tables listed in
    _REBUILDABLE_TABLES above -- not "every table except source_locators":
    cases/case_evidence/pulse_findings/finding_evidence are separate,
    not-yet-implemented Phase 2+ tables and this reset does not touch
    them. source_locators is the one table ingestion itself depends on
    that stays persistent; that manifest is what lets a deleted evidence
    unit stay deleted across a rebuild (CLAUDE.md 7.3, 18.3): rebuild only
    ever re-derives evidence_units for source_locators rows that still
    exist."""
    # Dropping evidence_units with foreign keys ON would cascade-delete every
    # case_evidence / finding_evidence row, silently destroying the dependency
    # record deletion relies on (CLAUDE.md 18.2). Evidence IDs are stable across
    # a rebuild, so those references are valid again once the units are
    # recreated; enforcement is switched off only for the drops themselves.
    conn.commit()  # PRAGMA foreign_keys is a no-op inside a transaction
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for table in _REBUILDABLE_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
