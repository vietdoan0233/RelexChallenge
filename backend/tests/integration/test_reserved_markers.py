"""Full-pipeline guarantees for reserved redaction markers (CLAUDE.md
18.7): a marker must never become a person/alias or receive an
AUTHOR/SPEAKER/MENTIONED relation, while the marker-bearing content it
replaces survives ingestion and named people elsewhere in the same
corpus are unaffected. Exercised through the full ingest() path, not
just the individual parsers, since the failure mode this guards against
(a sanitized speaker_sender quietly becoming a brand new fake person)
only shows up once people.seed_and_discover and service._link_relations
both run against real parsed documents.
"""

from pathlib import Path

from app.core import anonymous_labels
from app.core.enums import PersonRelation
from app.db import repository
from app.ingestion.service import ingest

_TRANSCRIPT = (
    "Meeting: Weekly sync\nCustomer: Acme Org\nDate: 2024-07-09\nPhase: Implementation\n"
    "Attendees: Marco Rossi (RELEX), Lena Fischer (Acme)\n\n"
    "Marco Rossi\n0:050:05\nMR\nMarco Rossi 5 seconds\n"
    "Let's start the weekly sync.\n"
    "[REDACTED SPEAKER]\n0:100:10\n"
    "[REDACTED SPEAKER] 10 seconds\n"
    "We discussed the reorg privately.\n"
    "Lena Fischer\n0:150:15\nLF\nLena Fischer 15 seconds\n"
    "Thanks, moving on.\n"
)
_EMAIL = (
    "Subject: Status\n"
    "From: Marco Rossi <marco.rossi@example.com>\n"
    "Date: Thursday, October 30, 2025 12:02 PM\n"
    "To: Lena Fischer <lena.fischer@example.com>\n"
    "Messages in thread: 2\n\n"
    "Hi All, hereby the weekly update.\n\n"
    "From: [REDACTED SENDER]\n"
    "Sent: Thursday, September 4, 2025 14:20\n"
    "To: Marco Rossi <marco.rossi@example.com>\n"
    "Subject: Re: Status\n\n"
    "Following up on the below.\n"
)


def _write_corpus(root: Path) -> None:
    (root / "transcripts").mkdir(parents=True, exist_ok=True)
    (root / "emails").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "transcripts" / "01_weekly-sync.txt").write_text(_TRANSCRIPT, encoding="utf-8")
    (root / "emails" / "01_status.txt").write_text(_EMAIL, encoding="utf-8")


def test_reserved_markers_never_become_people_aliases_or_relations(tmp_path, conn):
    source = tmp_path / "source"
    _write_corpus(source)

    report = ingest(conn, source, embedding_provider=None)

    for marker in anonymous_labels.REDACTION_MARKERS:
        assert repository.find_person_id_by_canonical_name(conn, marker) is None
        assert marker not in {row["alias"] for row in repository.all_aliases(conn)}
        assert marker not in report.rejected_candidates
        assert marker not in report.unresolved_alias_candidates

    units = {row["raw_text"]: row for row in repository.all_evidence_units(conn)}
    assert "We discussed the reorg privately." in units
    assert "Following up on the below." in units

    redacted_speaker_unit = units["We discussed the reorg privately."]
    redacted_sender_unit = units["Following up on the below."]
    assert redacted_speaker_unit["speaker_sender"] == "[REDACTED SPEAKER]"
    assert redacted_sender_unit["speaker_sender"] == "[REDACTED SENDER]"

    for unit in (redacted_speaker_unit, redacted_sender_unit):
        relations = repository.evidence_people_for(conn, unit["evidence_id"])
        assert relations == [], f"marker unit got a person relation: {list(relations)}"

    # Named people elsewhere in the same corpus are unaffected.
    marco_id = repository.find_person_id_by_canonical_name(conn, "Marco Rossi")
    lena_id = repository.find_person_id_by_canonical_name(conn, "Lena Fischer")
    assert marco_id is not None
    assert lena_id is not None

    marco_turn = units["Let's start the weekly sync."]
    lena_turn = units["Thanks, moving on."]
    assert (marco_id, PersonRelation.SPEAKER.value) in [
        (r["person_id"], r["relation"])
        for r in repository.evidence_people_for(conn, marco_turn["evidence_id"])
    ]
    assert (lena_id, PersonRelation.SPEAKER.value) in [
        (r["person_id"], r["relation"])
        for r in repository.evidence_people_for(conn, lena_turn["evidence_id"])
    ]

    email_author_unit = units["Hi All, hereby the weekly update."]
    assert (marco_id, PersonRelation.AUTHOR.value) in [
        (r["person_id"], r["relation"])
        for r in repository.evidence_people_for(conn, email_author_unit["evidence_id"])
    ]


def test_reserved_markers_stay_absent_after_rebuild(tmp_path, conn):
    source = tmp_path / "source"
    _write_corpus(source)

    ingest(conn, source, embedding_provider=None)
    ingest(conn, source, embedding_provider=None)

    for marker in anonymous_labels.REDACTION_MARKERS:
        assert repository.find_person_id_by_canonical_name(conn, marker) is None
    people_count = repository.people_row_count(conn)
    assert people_count == 2  # Marco Rossi, Lena Fischer -- never grows from re-ingestion
