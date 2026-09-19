import sqlite3

from app.db.connection import apply_schema

# Tables ingestion fully regenerates from data/source/ (plus the reviewed
# identity manifest, for people/person_aliases, and source_locators, for
# evidence_units) on every run. Dropping them before re-ingesting is what
# makes rebuild idempotent instead of accumulating duplicates -- and, for
# people/person_aliases specifically, what stops a stale false identity
# from a earlier, looser extraction pass from surviving forever just
# because INSERT OR IGNORE never removes anything. Identity is derived
# fresh each run from two sanitizable inputs (data/source/ and
# data/source/reviewed_identities.json), so dropping and rebuilding it is
# safe: a deleted person's traces are already gone from both inputs by
# the time a rebuild runs.
_REBUILDABLE_TABLES = [
    "evidence_fts",
    "evidence_embeddings",
    "evidence_people",
    "person_aliases",
    "people",
    "evidence_units",
    "documents",
]


def initialize(conn: sqlite3.Connection) -> None:
    apply_schema(conn)


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
    for table in _REBUILDABLE_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    apply_schema(conn)
