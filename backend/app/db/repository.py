import hashlib
import re
import sqlite3

from app.core.enums import PersonRelation
from app.schemas.evidence import Document, EvidenceUnit


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# fingerprint() always produces 16 lowercase hex characters. This
# sentinel is neither shaped like one nor derived from any content, so a
# revoked row's overwritten fingerprint can never real-match a freshly
# computed fingerprint during ingestion (CLAUDE.md 18.8).
REVOKED_FINGERPRINT_SENTINEL = "REVOKED"


class LocatorNotFoundError(LookupError):
    """Raised by revoke_source_locator when no row exists for the given
    (document_id, source_locator). Revocation targets a specific,
    already-assigned locator; silently no-oping on a typo'd or
    never-assigned locator would hide a real bug."""


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "x"


# ---------------------------------------------------------------- documents


def upsert_document(conn: sqlite3.Connection, doc: Document) -> None:
    conn.execute(
        """
        INSERT INTO documents
            (document_id, filename, document_type, title, source_date, thread_context)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id) DO UPDATE SET
            filename=excluded.filename,
            document_type=excluded.document_type,
            title=excluded.title,
            source_date=excluded.source_date,
            thread_context=excluded.thread_context
        """,
        (
            doc.document_id,
            doc.filename,
            doc.document_type.value,
            doc.title,
            doc.source_date,
            doc.thread_context,
        ),
    )


def all_documents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM documents").fetchall()


# ------------------------------------------------------------ evidence units


def insert_evidence_unit(conn: sqlite3.Connection, unit: EvidenceUnit) -> None:
    conn.execute(
        """
        INSERT INTO evidence_units
            (evidence_id, document_id, source_locator, unit_index, speaker_sender,
             event_date, timestamp_text, thread_context, raw_text, text_hash, is_truncated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            unit.evidence_id,
            unit.document_id,
            unit.source_locator,
            unit.unit_index,
            unit.speaker_sender,
            unit.event_date,
            unit.timestamp_text,
            unit.thread_context,
            unit.raw_text,
            unit.text_hash,
            int(unit.is_truncated),
        ),
    )


def all_evidence_units(
    conn: sqlite3.Connection, document_id: str | None = None
) -> list[sqlite3.Row]:
    if document_id:
        return conn.execute(
            "SELECT * FROM evidence_units WHERE document_id = ? ORDER BY unit_index", (document_id,)
        ).fetchall()
    return conn.execute("SELECT * FROM evidence_units ORDER BY document_id, unit_index").fetchall()


def insert_fts_row(conn: sqlite3.Connection, evidence_id: str, raw_text: str) -> None:
    conn.execute(
        "INSERT INTO evidence_fts (evidence_id, raw_text) VALUES (?, ?)",
        (evidence_id, raw_text),
    )


def fts_row_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM evidence_fts").fetchone()["n"]


def insert_embedding(
    conn: sqlite3.Connection, evidence_id: str, model_name: str, vector_json: str
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO evidence_embeddings (evidence_id, model_name, vector_json) "
        "VALUES (?, ?, ?)",
        (evidence_id, model_name, vector_json),
    )


def embedding_row_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM evidence_embeddings").fetchone()["n"]


# ------------------------------------------------------------------- people


def get_or_create_person(conn: sqlite3.Connection, canonical_name: str) -> str:
    person_id = slugify(canonical_name)
    conn.execute(
        "INSERT OR IGNORE INTO people (person_id, canonical_name) VALUES (?, ?)",
        (person_id, canonical_name),
    )
    return person_id


def find_person_id_by_canonical_name(conn: sqlite3.Connection, canonical_name: str) -> str | None:
    row = conn.execute(
        "SELECT person_id FROM people WHERE canonical_name = ?", (canonical_name,)
    ).fetchone()
    return row["person_id"] if row else None


def add_alias(conn: sqlite3.Connection, person_id: str, alias: str, alias_type: str) -> None:
    alias_id = f"AL-{slugify(person_id + '-' + alias)}"
    conn.execute(
        "INSERT OR IGNORE INTO person_aliases (alias_id, person_id, alias, alias_type) "
        "VALUES (?, ?, ?, ?)",
        (alias_id, person_id, alias, alias_type),
    )


def find_person_ids_by_alias(conn: sqlite3.Connection, alias: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT person_id FROM person_aliases WHERE alias = ?", (alias,)
    ).fetchall()
    return [row["person_id"] for row in rows]


def all_people(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT person_id, canonical_name FROM people ORDER BY canonical_name"
    ).fetchall()


def people_row_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM people").fetchone()["n"]


def alias_row_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM person_aliases").fetchone()["n"]


def relation_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT relation, COUNT(*) AS n FROM evidence_people GROUP BY relation"
    ).fetchall()
    return {row["relation"]: row["n"] for row in rows}


def all_aliases(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT alias_id, person_id, alias, alias_type FROM person_aliases "
        "ORDER BY person_id, alias"
    ).fetchall()


def link_evidence_person(
    conn: sqlite3.Connection, evidence_id: str, person_id: str, relation: PersonRelation
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO evidence_people (evidence_id, person_id, relation) VALUES (?, ?, ?)",
        (evidence_id, person_id, relation.value),
    )


def evidence_people_for(conn: sqlite3.Connection, evidence_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT person_id, relation FROM evidence_people WHERE evidence_id = ?", (evidence_id,)
    ).fetchall()


# --------------------------------------------------------- source locators


def load_locator_manifest(conn: sqlite3.Connection, document_id: str) -> list[sqlite3.Row]:
    """Existing LIVE (non-revoked) (locator, fingerprint) pairs for a
    document, in the order they were first assigned. This genesis
    ordering -- not the current file's ordering -- is what makes
    rebuild-after-delete safe. A revoked row (revoked_at IS NOT NULL) is
    excluded so its sentinel fingerprint can never real-match new
    content and a revoked locator can never be silently reassigned via
    manifest-based fingerprint matching (CLAUDE.md 18.8)."""
    return conn.execute(
        "SELECT source_locator, content_fingerprint, genesis_position FROM source_locators "
        "WHERE document_id = ? AND revoked_at IS NULL ORDER BY genesis_position",
        (document_id,),
    ).fetchall()


def next_genesis_position(conn: sqlite3.Connection, document_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(genesis_position), -1) + 1 AS next "
        "FROM source_locators WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    return row["next"]


def find_locator_row(
    conn: sqlite3.Connection, document_id: str, source_locator: str
) -> sqlite3.Row | None:
    """The existing (genesis_position, revoked_at) row for
    (document_id, source_locator), or None if it was never assigned.
    Distinguishing a live row from a revoked one is what lets
    locator_manifest.assign_natural_locator refuse to silently resurrect
    a revoked locator instead of just checking whether a row exists."""
    return conn.execute(
        "SELECT genesis_position, revoked_at FROM source_locators "
        "WHERE document_id = ? AND source_locator = ?",
        (document_id, source_locator),
    ).fetchone()


def record_source_locator(
    conn: sqlite3.Connection,
    document_id: str,
    source_locator: str,
    content_fingerprint: str,
    genesis_position: int,
    first_seen_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO source_locators
            (document_id, source_locator, content_fingerprint, genesis_position, first_seen_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (document_id, source_locator, content_fingerprint, genesis_position, first_seen_at),
    )


def revoke_source_locator(
    conn: sqlite3.Connection, document_id: str, source_locator: str, revoked_at: str
) -> None:
    """Tombstones a source_locators row in place for a fully-deleted
    Evidence Unit (CLAUDE.md 18.8). The row itself, and its document_id/
    source_locator/genesis_position/first_seen_at, are preserved
    forever -- this never DELETEs the row, so next_genesis_position's
    high-water mark can never shrink and this exact locator string can
    never be reassigned. content_fingerprint is overwritten with
    REVOKED_FINGERPRINT_SENTINEL so the row can never real-match a
    freshly computed fingerprint again.

    Idempotent: revoking an already-revoked row is a safe no-op that
    preserves the original revoked_at and never re-touches the
    fingerprint a second time. Raises LocatorNotFoundError if no row
    exists at all for (document_id, source_locator).
    """
    row = conn.execute(
        "SELECT revoked_at FROM source_locators WHERE document_id = ? AND source_locator = ?",
        (document_id, source_locator),
    ).fetchone()
    if row is None:
        raise LocatorNotFoundError(
            f"no source_locators row for document_id={document_id!r}, "
            f"source_locator={source_locator!r}"
        )
    if row["revoked_at"] is not None:
        return
    conn.execute(
        "UPDATE source_locators SET revoked_at = ?, content_fingerprint = ? "
        "WHERE document_id = ? AND source_locator = ?",
        (revoked_at, REVOKED_FINGERPRINT_SENTINEL, document_id, source_locator),
    )
