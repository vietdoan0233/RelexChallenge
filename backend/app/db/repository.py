import hashlib
import re
import secrets
import sqlite3
import uuid

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


def insert_fts_row(
    conn: sqlite3.Connection,
    evidence_id: str,
    raw_text: str,
    thread_context: str | None = None,
    speaker_sender: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO evidence_fts (evidence_id, raw_text, thread_context, speaker_sender) "
        "VALUES (?, ?, ?, ?)",
        (evidence_id, raw_text, thread_context or "", speaker_sender or ""),
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
#
# Architecture v1.6 (CLAUDE.md 18.0): subject_id is a cryptographically
# random UUID and display_alias is generated independently, just as
# randomly -- neither is ever derived from a name, so there is no
# get_or_create-by-slugify shortcut left. Resolving a structural name to a
# subject_id means matching it against what is already known (an existing
# FULL_NAME alias, or an existing display_alias when the name found in the
# source *is* someone's own alias -- see find_subject_id_by_structural_name)
# and only minting a new subject when nothing matches.

# No 0/O/1/I: this alphabet is for a human-facing label that a judge or
# reviewer may need to read aloud or type back, not for security entropy
# (the code is public by design -- it is the *replacement* for a name, not
# a secret). Collision handling in generate_unique_display_alias retries
# with a fresh random draw; it never falls back to a counter or any other
# predictable sequence.
_ALIAS_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_subject_id() -> str:
    """A cryptographically secure random UUID (uuid4 draws from os.urandom)
    containing no name-derived material."""
    return str(uuid.uuid4())


def _random_alias_code(length: int) -> str:
    return "".join(secrets.choice(_ALIAS_ALPHABET) for _ in range(length))


def generate_display_alias() -> str:
    """`Participant Q7M4-N8`-shaped label. The literal format is a display
    convention, not a derivation algorithm -- nothing about a given
    person's name, email, or subject_id feeds into it."""
    return f"Participant {_random_alias_code(4)}-{_random_alias_code(2)}"


def generate_unique_display_alias(conn: sqlite3.Connection, max_attempts: int = 50) -> str:
    for _ in range(max_attempts):
        candidate = generate_display_alias()
        exists = conn.execute(
            "SELECT 1 FROM people WHERE display_alias = ?", (candidate,)
        ).fetchone()
        if exists is None:
            return candidate
    # Astronomically unlikely at this alphabet size (32^6 codes) and a
    # 45-document corpus's worth of people; fail loudly rather than ever
    # falling back to a predictable/incrementing suffix.
    raise RuntimeError("could not generate a unique display alias")


def find_subject_id_by_structural_name(conn: sqlite3.Connection, name: str) -> str | None:
    """Resolve a speaker/sender/attendee string found in the source to an
    existing subject, checking both of the two ways that string can
    legitimately already belong to someone:

    1. it is an ACTIVE person's canonical full name (a FULL_NAME alias), or
    2. it is a PSEUDONYMISED person's own display_alias -- the literal text
       their name was rewritten to, which is exactly what a later ingest of
       the rewritten source will find in that speaker/sender position.

    Returns None only when neither is true, i.e. this is a genuinely new
    person. Never matches on a bare short-form alias (first name, initials,
    ...); those are handled separately by the reviewed-manifest mention path.
    """
    row = conn.execute("SELECT subject_id FROM people WHERE display_alias = ?", (name,)).fetchone()
    if row is not None:
        return row["subject_id"]
    row = conn.execute(
        "SELECT subject_id FROM person_aliases WHERE alias = ? AND alias_type = 'FULL_NAME'",
        (name,),
    ).fetchone()
    return row["subject_id"] if row else None


def get_or_create_subject(conn: sqlite3.Connection, display_name: str) -> str:
    """Idempotent across ingestion runs: the same structural name always
    resolves to the same subject_id (see find_subject_id_by_structural_name),
    so a rebuild can never mint a second identity for someone already known.
    Only inserts the people row itself -- callers add the FULL_NAME alias
    (see app/ingestion/people.py), so a caller that already knows this is a
    known display_alias can skip that step entirely."""
    existing = find_subject_id_by_structural_name(conn, display_name)
    if existing is not None:
        return existing
    subject_id = generate_subject_id()
    display_alias = generate_unique_display_alias(conn)
    conn.execute(
        "INSERT INTO people (subject_id, display_alias, privacy_state, display_name) "
        "VALUES (?, ?, 'ACTIVE', ?)",
        (subject_id, display_alias, display_name),
    )
    return subject_id


def is_known_display_alias(conn: sqlite3.Connection, name: str) -> bool:
    """True when `name` is already someone's display_alias -- i.e. this is
    not a new person to discover, it is the alias-rewritten trace of an
    already-pseudonymised one (CLAUDE.md 18.0: 'never treat Participant
    Q7M4-N8 as a new real person')."""
    return (
        conn.execute("SELECT 1 FROM people WHERE display_alias = ?", (name,)).fetchone() is not None
    )


def add_alias(conn: sqlite3.Connection, subject_id: str, alias: str, alias_type: str) -> None:
    alias_id = f"AL-{uuid.uuid4().hex}"
    conn.execute(
        "INSERT OR IGNORE INTO person_aliases (alias_id, subject_id, alias, alias_type) "
        "VALUES (?, ?, ?, ?)",
        (alias_id, subject_id, alias, alias_type),
    )


def find_subject_ids_by_alias(conn: sqlite3.Connection, alias: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT subject_id FROM person_aliases WHERE alias = ?", (alias,)
    ).fetchall()
    return [row["subject_id"] for row in rows]


def all_people(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT subject_id, display_alias, privacy_state, display_name FROM people "
        "ORDER BY COALESCE(display_name, display_alias)"
    ).fetchall()


def get_person(conn: sqlite3.Connection, subject_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM people WHERE subject_id = ?", (subject_id,)).fetchone()


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
        "SELECT alias_id, subject_id, alias, alias_type FROM person_aliases "
        "ORDER BY subject_id, alias"
    ).fetchall()


def prune_orphaned_active_people(conn: sqlite3.Connection) -> int:
    """After evidence_people is fully rebuilt for a run, remove any ACTIVE
    person left with zero evidence_people rows: either stale contamination
    from an earlier, looser extraction pass, or a name that no longer
    appears in data/source/ at all. This restores the self-healing property
    the old fully-rebuildable people table used to give for free, without
    weakening identity stability for anyone actually still present: a
    PSEUDONYMISED subject is never a candidate here regardless of its
    current evidence count (CLAUDE.md 18.0.1: the participant row is never
    deleted), and an ACTIVE person genuinely still in the corpus always has
    at least one surviving evidence_people row. Returns the number removed.
    Must run after evidence_people is repopulated, never before."""
    conn.execute(
        "DELETE FROM person_aliases WHERE subject_id IN ("
        "  SELECT p.subject_id FROM people p"
        "  LEFT JOIN evidence_people ep ON ep.subject_id = p.subject_id"
        "  WHERE p.privacy_state = 'ACTIVE' AND ep.evidence_id IS NULL"
        ")"
    )
    cursor = conn.execute(
        "DELETE FROM people WHERE privacy_state = 'ACTIVE' AND subject_id NOT IN "
        "(SELECT DISTINCT subject_id FROM evidence_people)"
    )
    return cursor.rowcount


def link_evidence_person(
    conn: sqlite3.Connection, evidence_id: str, subject_id: str, relation: PersonRelation
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO evidence_people (evidence_id, subject_id, relation) "
        "VALUES (?, ?, ?)",
        (evidence_id, subject_id, relation.value),
    )


def evidence_people_for(conn: sqlite3.Connection, evidence_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT subject_id, relation FROM evidence_people WHERE evidence_id = ?", (evidence_id,)
    ).fetchall()


def evidence_for_subject(conn: sqlite3.Connection, subject_id: str) -> list[sqlite3.Row]:
    """Every Evidence Unit (plus its document/thread metadata) in which this
    subject is an AUTHOR, SPEAKER, or MENTIONED participant -- the DB-hydrated
    source of a participant's full clickable history (CLAUDE.md 18.0.2).
    Never touches the vault."""
    return conn.execute(
        "SELECT e.evidence_id, e.document_id, e.unit_index, e.speaker_sender, e.event_date, "
        "       e.timestamp_text, e.thread_context, e.raw_text, e.is_truncated, ep.relation, "
        "       d.filename, d.document_type, d.title AS document_title "
        "FROM evidence_people ep "
        "JOIN evidence_units e ON e.evidence_id = ep.evidence_id "
        "JOIN documents d ON d.document_id = e.document_id "
        "WHERE ep.subject_id = ? "
        "ORDER BY e.event_date, e.document_id, e.unit_index",
        (subject_id,),
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
        "SELECT source_locator, content_fingerprint, genesis_position, starts_group "
        "FROM source_locators "
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
        "SELECT genesis_position, revoked_at, starts_group FROM source_locators "
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


# ------------------------------------------------------------------- cases


def save_case(
    conn: sqlite3.Connection,
    *,
    case_id: str,
    query: str,
    receipt_json: str,
    created_at: str,
    evidence_usage: dict[str, set[str]],
) -> None:
    """Persist a validated, ids-only receipt and its evidence references.

    case_evidence is what lets a later deletion find and invalidate every
    Case that depended on a unit (CLAUDE.md 18.2).
    """
    conn.execute(
        "INSERT OR REPLACE INTO cases (case_id, query, receipt_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (case_id, query, receipt_json, created_at, created_at),
    )
    conn.execute("DELETE FROM case_evidence WHERE case_id = ?", (case_id,))
    for usage, ids in evidence_usage.items():
        for evidence_id in sorted(ids):
            conn.execute(
                "INSERT OR IGNORE INTO case_evidence (case_id, evidence_id, usage) "
                "VALUES (?, ?, ?)",
                (case_id, evidence_id, usage),
            )


def load_case(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()


def record_group_start(
    conn: sqlite3.Connection, document_id: str, source_locator: str, starts_group: bool
) -> None:
    """Persist a fragment's group boundary once. Never overwrites a recorded
    value: the boundary that existed at genesis is the one that must hold."""
    conn.execute(
        "UPDATE source_locators SET starts_group = ? "
        "WHERE document_id = ? AND source_locator = ? AND starts_group IS NULL",
        (int(starts_group), document_id, source_locator),
    )
