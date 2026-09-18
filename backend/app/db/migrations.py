import sqlite3

from app.db.connection import apply_schema

# Tables ingestion fully regenerates from data/source/ plus the persistent
# tables below, on every run. Dropping them before re-ingesting is what
# makes rebuild idempotent instead of accumulating duplicates.
_REBUILDABLE_TABLES = [
    "evidence_fts",
    "evidence_embeddings",
    "evidence_people",
    "evidence_units",
    "documents",
]


def initialize(conn: sqlite3.Connection) -> None:
    apply_schema(conn)


def reset_rebuildable_tables(conn: sqlite3.Connection) -> None:
    """Drop and recreate the tables ingestion fully regenerates, leaving
    people, person_aliases, and source_locators untouched. Those three
    persistent tables are what let a deleted person or an earlier deleted
    evidence unit stay deleted across a rebuild (CLAUDE.md 7.3, 18.3):
    rebuild only ever re-derives evidence_units from source_locators rows
    that still exist, and never re-seeds a person removed from `people`.
    """
    for table in _REBUILDABLE_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    apply_schema(conn)
