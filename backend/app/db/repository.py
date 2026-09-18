import hashlib
import re
import sqlite3

from app.core.enums import PersonRelation
from app.schemas.evidence import Document, EvidenceUnit


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


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
    """Existing (locator, fingerprint) pairs for a document, in the order
    they were first assigned. This genesis ordering -- not the current
    file's ordering -- is what makes rebuild-after-delete safe."""
    return conn.execute(
        "SELECT source_locator, content_fingerprint, genesis_position FROM source_locators "
        "WHERE document_id = ? ORDER BY genesis_position",
        (document_id,),
    ).fetchall()


def next_genesis_position(conn: sqlite3.Connection, document_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(genesis_position), -1) + 1 AS next "
        "FROM source_locators WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    return row["next"]


def find_locator_position(
    conn: sqlite3.Connection, document_id: str, source_locator: str
) -> int | None:
    row = conn.execute(
        "SELECT genesis_position FROM source_locators WHERE document_id = ? AND source_locator = ?",
        (document_id, source_locator),
    ).fetchone()
    return row["genesis_position"] if row else None


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


def delete_source_locator(conn: sqlite3.Connection, document_id: str, source_locator: str) -> None:
    conn.execute(
        "DELETE FROM source_locators WHERE document_id = ? AND source_locator = ?",
        (document_id, source_locator),
    )
