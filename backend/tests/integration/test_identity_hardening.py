"""Full-pipeline identity hardening guarantees: identity rows are a pure,
idempotent function of data/source/ plus the reviewed identity manifest,
so a stale false identity from an earlier, looser extraction pass cannot
outlive the ingestion run that produced it, and the ingestion report's
people/alias/relationship counts are read back from the database rather
than trusted from attempted-insert tallies.
"""

import json
from pathlib import Path

import pytest

from app.db import repository
from app.ingestion.people import ManifestValidationError
from app.ingestion.service import ingest

_TRANSCRIPT = (
    "Meeting: Weekly sync\nCustomer: Acme Org\nDate: 2024-07-09\nPhase: Implementation\n"
    "Attendees: Marco Rossi (RELEX), Sofia Almeida (Acme)\n\n"
    "Marco Rossi\n0:050:05\nMR\nMarco Rossi 5 seconds\n"
    "Tobias Ekström flagged this before he left.\n"
    "Sofia Almeida\n0:100:10\nSA\nSofia Almeida 10 seconds\n"
    "Risk Fresh Phase two is behind schedule.\n"
)
_EMAIL = (
    "Subject: Status\nFrom: Marco Rossi <marco.rossi@example.com>\n"
    "Date: Thursday, October 30, 2025 12:02 PM\nTo: Sofia Almeida <sofia.almeida@example.com>\n"
    "Messages in thread: 1\n\nHi All, hereby the weekly update.\n"
)
_MANIFEST = {
    "description": "test",
    "entries": [
        {
            "canonical_name": "Tobias Ekström",
            "verified_aliases": [],
            "review_note": "Departed employee, mentioned once.",
        }
    ],
}


def _write_corpus(root: Path) -> None:
    (root / "transcripts").mkdir(parents=True, exist_ok=True)
    (root / "emails").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "transcripts" / "01_weekly-sync.txt").write_text(_TRANSCRIPT, encoding="utf-8")
    (root / "emails" / "01_status.txt").write_text(_EMAIL, encoding="utf-8")
    (root / "reviewed_identities.json").write_text(json.dumps(_MANIFEST), encoding="utf-8")


def test_repeated_ingestion_produces_identical_identity_rows(tmp_path, conn):
    source = tmp_path / "source"
    _write_corpus(source)

    ingest(conn, source, embedding_provider=None)
    people_after_first = {
        row["subject_id"]: row["display_name"] for row in repository.all_people(conn)
    }
    aliases_after_first = {
        (row["subject_id"], row["alias"]) for row in repository.all_aliases(conn)
    }

    ingest(conn, source, embedding_provider=None)
    people_after_second = {
        row["subject_id"]: row["display_name"] for row in repository.all_people(conn)
    }
    aliases_after_second = {
        (row["subject_id"], row["alias"]) for row in repository.all_aliases(conn)
    }

    # Architecture v1.6: identity is persistent (CLAUDE.md 18.0), so this is
    # no longer just "the same names come back" -- it is the *same*
    # subject_id for each of them, proving a rebuild never mints a second
    # identity for someone already known.
    assert people_after_first == people_after_second
    assert aliases_after_first == aliases_after_second


def test_contaminated_identity_rows_are_pruned_on_rebuild(tmp_path, conn):
    """Architecture v1.6 replaces the old fully-rebuildable people table
    (which self-healed by being dropped every run) with a persistent one
    that must instead prune away exactly the rows nothing in the current
    source/manifest resolves to (repository.prune_orphaned_active_people,
    called from ingest()) -- restoring the same self-healing guarantee
    without weakening subject_id stability for anyone genuinely still
    present.

    The stray name below is deliberately synthetic and absent from
    _TRANSCRIPT/_EMAIL: a name that happens to also appear verbatim in real
    corpus text (e.g. this module's own "Risk Fresh Phase" false-positive
    fixture) would legitimately earn a MENTIONED relation from the mention
    scan and *should* survive -- that is a different, correctly-working
    code path (app/ingestion/people.py's _unique_short_name_owners), not
    the orphan case this test isolates. The realistic version of this
    failure mode is a person whose name was subsequently removed from
    data/source/ entirely, or a stray direct-DB insert (an earlier,
    looser extraction pass) that never corresponds to anything in the
    current corpus at all."""
    source = tmp_path / "source"
    _write_corpus(source)

    stray_subject_id = repository.get_or_create_subject(conn, "Zzyx Orphaned Contamination")
    repository.add_alias(conn, stray_subject_id, "Zzyx Orphaned Contamination", "FULL_NAME")
    repository.add_alias(conn, stray_subject_id, "Zzyxvariant", "NICKNAME")
    conn.commit()
    assert (
        repository.find_subject_id_by_structural_name(conn, "Zzyx Orphaned Contamination")
        is not None
    )

    ingest(conn, source, embedding_provider=None)

    assert (
        repository.find_subject_id_by_structural_name(conn, "Zzyx Orphaned Contamination") is None
    )
    assert repository.find_subject_ids_by_alias(conn, "Zzyxvariant") == []


def test_report_counts_match_actual_sql_counts(tmp_path, conn):
    source = tmp_path / "source"
    _write_corpus(source)

    report = ingest(conn, source, embedding_provider=None)

    assert report.people_count == repository.people_row_count(conn)
    assert report.alias_count == repository.alias_row_count(conn)
    assert report.relation_counts == repository.relation_counts(conn)
    assert report.people_count > 0
    assert sum(report.relation_counts.values()) > 0


def test_reviewed_manifest_person_survives_rebuild_alongside_structural_people(tmp_path, conn):
    source = tmp_path / "source"
    _write_corpus(source)

    ingest(conn, source, embedding_provider=None)

    assert repository.find_subject_id_by_structural_name(conn, "Tobias Ekström") is not None
    assert repository.find_subject_id_by_structural_name(conn, "Marco Rossi") is not None
    assert repository.find_subject_id_by_structural_name(conn, "Risk Fresh Phase") is None


def test_malformed_manifest_fails_before_destructive_reset(tmp_path, conn):
    """The destructive rebuildable-table reset must not run until the
    source and manifest have been parsed and validated -- otherwise a bad
    manifest edit would empty an existing database before failing."""
    source = tmp_path / "source"
    _write_corpus(source)
    ingest(conn, source, embedding_provider=None)
    people_before = repository.people_row_count(conn)
    units_before = len(repository.all_evidence_units(conn))
    assert people_before > 0
    assert units_before > 0

    (source / "reviewed_identities.json").write_text(
        json.dumps({"description": "bad", "entries": [{"canonical_name": "No Review Note"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ManifestValidationError):
        ingest(conn, source, embedding_provider=None)

    assert repository.people_row_count(conn) == people_before
    assert len(repository.all_evidence_units(conn)) == units_before


def test_source_locators_persist_across_identity_rebuild(tmp_path, conn):
    """source_locators, like people/person_aliases (Architecture v1.6,
    CLAUDE.md 18.0), is persistent across rebuild -- this is what keeps
    Evidence IDs stable across the same rebuild that re-links identity."""
    source = tmp_path / "source"
    _write_corpus(source)

    ingest(conn, source, embedding_provider=None)
    before = {row["evidence_id"] for row in repository.all_evidence_units(conn)}

    ingest(conn, source, embedding_provider=None)
    after = {row["evidence_id"] for row in repository.all_evidence_units(conn)}

    assert before == after
    assert len(before) > 0
