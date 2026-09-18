"""Assigns stable source locators and derives the resulting stable
evidence_id. CLAUDE.md 7.3: an evidence_id must never shift for a
surviving unit just because an earlier unit in the same document was
deleted, so a locator is captured once (at genesis) and looked up --
never recomputed from the current unit count -- on every later rebuild.

Locators are assigned per raw fragment, before any same-speaker merging,
and every assignment carries its genesis_position alongside the locator
string. This is what lets the merge step tell a genuinely continuous
utterance (adjacent fragments whose genesis positions are consecutive)
apart from two fragments that only look adjacent because whatever used
to sit between them at genesis has since been deleted (a gap in genesis
position) -- without that, deleting one turn from an alternating
two-party dialogue would fuse its two now-neighboring survivors into a
turn that never actually happened as one continuous utterance.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db import repository


@dataclass(frozen=True)
class LocatorAssignment:
    source_locator: str
    genesis_position: int


def evidence_id_for(document_id: str, source_locator: str) -> str:
    return f"EV-{document_id}-{source_locator}"


def assign_manifest_locators(
    conn: sqlite3.Connection, document_id: str, fingerprints: list[str]
) -> list[LocatorAssignment]:
    """For fragments with no natural stable identifier (anonymous
    transcript turns, report bullets): given the content fingerprints of
    a document's fragments in the order the current parse produced them,
    return each one's stable assignment. A fingerprint that matches a
    prior assignment reuses it; a fingerprint appearing more times than
    it did at genesis (i.e. never seen before) mints a fresh one. Content
    hash alone is not used as identity -- position-among-duplicates via
    `consumed` disambiguates fragments with byte-identical text."""
    existing = repository.load_locator_manifest(conn, document_id)

    by_fingerprint: dict[str, list[tuple[str, int]]] = {}
    for row in existing:
        by_fingerprint.setdefault(row["content_fingerprint"], []).append(
            (row["source_locator"], row["genesis_position"])
        )

    consumed: dict[str, int] = {}
    next_position = repository.next_genesis_position(conn, document_id)
    now = datetime.now(UTC).isoformat()

    assignments: list[LocatorAssignment] = []
    for fp in fingerprints:
        bucket = by_fingerprint.get(fp, [])
        idx = consumed.get(fp, 0)
        if idx < len(bucket):
            locator, position = bucket[idx]
        else:
            locator, position = f"u{next_position:04d}", next_position
            repository.record_source_locator(conn, document_id, locator, fp, position, now)
            next_position += 1
        consumed[fp] = idx + 1
        assignments.append(LocatorAssignment(locator, position))
    return assignments


def assign_natural_locator(
    conn: sqlite3.Connection, document_id: str, natural_locator: str, fp: str
) -> LocatorAssignment:
    """For fragments with an inherently stable, source-embedded locator
    (an email's Date header, a transcript turn's timestamp): record it in
    the manifest for its genesis_position, but the locator value itself
    needs no fingerprint matching since it is already stable by
    construction. Recording is idempotent -- INSERT OR IGNORE -- so
    re-ingestion keeps the original genesis_position/first_seen_at rather
    than overwriting them."""
    position = repository.find_locator_position(conn, document_id, natural_locator)
    if position is None:
        position = repository.next_genesis_position(conn, document_id)
        now = datetime.now(UTC).isoformat()
        repository.record_source_locator(conn, document_id, natural_locator, fp, position, now)
    return LocatorAssignment(natural_locator, position)
