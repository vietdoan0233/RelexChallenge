"""Runs the real ingestion pipeline against the actual challenge archive
in data/source/ (not a synthetic fixture), since Phase 1's exit criteria
is specifically that these 45 real, messy documents ingest correctly."""

from pathlib import Path

import pytest

from app.db import repository
from app.ingestion.service import enumerate_source_files, ingest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_DIR = _REPO_ROOT / "data" / "source"

pytestmark = pytest.mark.skipif(not _SOURCE_DIR.is_dir(), reason="data/source/ not present")


def test_all_45_archive_documents_are_enumerated():
    files = enumerate_source_files(_SOURCE_DIR)
    assert len(files) == 45
    by_subdir = {}
    for _path, subdir in files:
        by_subdir[subdir] = by_subdir.get(subdir, 0) + 1
    assert by_subdir == {"transcripts": 23, "emails": 20, "reports": 2}


def test_reference_material_outside_data_source_is_never_ingested(conn):
    ingest(conn, _SOURCE_DIR, embedding_provider=None)
    rows = conn.execute(
        "SELECT raw_text FROM evidence_units WHERE raw_text LIKE '%Nine questions%' "
        "OR raw_text LIKE '%graded set%'"
    ).fetchall()
    assert rows == []
    # ARCHIVE_README.md/PRACTICE_QUESTIONS.md live beside data/source/, not
    # inside it, and enumerate_source_files only walks emails/reports/
    # transcripts subdirectories -- so no document_id resembling them
    # should ever appear.
    doc_ids = {row["document_id"] for row in repository.all_documents(conn)}
    assert not any("README" in d or "PRACTICE" in d for d in doc_ids)


def test_full_ingestion_produces_the_expected_shape(conn):
    report = ingest(conn, _SOURCE_DIR, embedding_provider=None)

    assert report.documents_by_type == {"TRANSCRIPT": 23, "EMAIL": 20, "REPORT": 2}
    # From the archive's own README: 110 email messages across 20 threads.
    assert report.evidence_units_by_type["EMAIL"] == 110
    assert report.fts_row_count == sum(report.evidence_units_by_type.values())
    assert report.embeddings.skipped is True
    assert not report.parse_warnings


def test_every_evidence_unit_is_inspectable_by_its_evidence_id(conn):
    ingest(conn, _SOURCE_DIR, embedding_provider=None)
    rows = repository.all_evidence_units(conn)
    assert len(rows) > 0
    ids = [row["evidence_id"] for row in rows]
    assert len(ids) == len(set(ids)), "evidence_ids must be unique"
    for row in rows:
        assert row["evidence_id"].startswith(f"EV-{row['document_id']}-")


def test_kwame_boateng_is_a_known_person_with_evidence_links(conn):
    # The practice questions use Kwame Boateng as the deletion/pseudonymisation
    # test subject (P7); Architecture v1.6 depends on him being resolvable now.
    ingest(conn, _SOURCE_DIR, embedding_provider=None)
    subject_id = repository.find_subject_id_by_structural_name(conn, "Kwame Boateng")
    assert subject_id is not None
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM evidence_people WHERE subject_id = ?", (subject_id,)
    ).fetchone()
    assert rows["n"] > 0


def test_nadia_ambiguity_is_preserved_in_the_real_archive(conn):
    ingest(conn, _SOURCE_DIR, embedding_provider=None)
    haddad_id = repository.find_subject_id_by_structural_name(conn, "Nadia Haddad")
    assert haddad_id is not None
    matches = repository.find_subject_ids_by_alias(conn, "Nadia")
    assert matches == [], "a bare first name shared by two real people must stay unresolved"


def test_a_known_truncated_statement_is_flagged(conn):
    ingest(conn, _SOURCE_DIR, embedding_provider=None)
    row = conn.execute(
        "SELECT is_truncated FROM evidence_units WHERE raw_text LIKE '%obvious ones are%'"
    ).fetchone()
    assert row is not None
    assert row["is_truncated"] == 1


def test_real_archive_never_stores_known_false_positive_identities(conn):
    report = ingest(conn, _SOURCE_DIR, embedding_provider=None)
    rejected_names = {
        "Risk Fresh Phase",
        "Risk Still",
        "Slight Delay Bakery",
        "Bakery",
        "This So",
        "Not Nadia Öberg",
        "Hi All",
        "Data Protection Officer",
        "Chief Financial Officer",
    }
    for name in rejected_names:
        assert repository.find_subject_id_by_structural_name(conn, name) is None, name
    all_aliases = {row["alias"] for row in repository.all_aliases(conn)}
    assert not (rejected_names & all_aliases)
    assert report.people_count == repository.people_row_count(conn)
    assert report.alias_count == repository.alias_row_count(conn)


def test_real_archive_reviewed_text_only_people_are_confirmed(conn):
    ingest(conn, _SOURCE_DIR, embedding_provider=None)
    for name in ("Tobias Ekström", "Nadia Öberg", "Nils Ackermann"):
        assert repository.find_subject_id_by_structural_name(conn, name) is not None, name


def test_real_archive_repeated_ingestion_is_idempotent(conn):
    # Architecture v1.6: identity is now persistent (CLAUDE.md 18.0), so a
    # second ingest must resolve every structural name back to the *same*
    # subject_id -- not merely to the same set of display names -- and must
    # not mint a second identity for anyone already known.
    first = ingest(conn, _SOURCE_DIR, embedding_provider=None)
    people_first = {row["subject_id"]: row["display_name"] for row in repository.all_people(conn)}
    aliases_first = {(row["subject_id"], row["alias"]) for row in repository.all_aliases(conn)}

    second = ingest(conn, _SOURCE_DIR, embedding_provider=None)
    people_second = {row["subject_id"]: row["display_name"] for row in repository.all_people(conn)}
    aliases_second = {(row["subject_id"], row["alias"]) for row in repository.all_aliases(conn)}

    assert people_first == people_second
    assert aliases_first == aliases_second
    assert first.people_count == second.people_count
    assert first.alias_count == second.alias_count
