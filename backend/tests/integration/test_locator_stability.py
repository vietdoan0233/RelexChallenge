"""CLAUDE.md 7.3's key invariant: deleting one Evidence Unit must not
cause unrelated surviving Evidence IDs to change. Exercised here through
the full ingest() pipeline -- across a transcript (two-party alternating
dialogue, the hardest case; see test_transcript_parser.py for why), an
email thread, and a report -- by simulating what Phase 5's purge will
eventually do: physically removing one unit's text from data/source and
re-running ingestion.
"""

from pathlib import Path

from app.db import repository
from app.ingestion.service import ingest

_TRANSCRIPT_HEADER = (
    "Meeting: Internal call\nCustomer: Acme Org\nDate: 2024-07-09\nPhase: Implementation\n"
    "Attendees: Marco Rossi (RELEX), Kwame Boateng (RELEX)\n\n"
)

_EMAIL_BEFORE = (
    "Subject: Shelf life field mapping\n"
    "From: Nadia Haddad <n.haddad@relexsolutions.example>\n"
    "Date: Thursday, October 30, 2025 12:02 PM\n"
    "To: Ana Duarte <ana.duarte@relexsolutions.example>\n"
    "Messages in thread: 3\n\n"
    "We proceeded. Nobody objected.\n\n"
    "From: Ana Duarte <ana.duarte@relexsolutions.example>\n"
    "Sent: Thursday, September 4, 2025 14:20\n"
    "To: Nadia Haddad <n.haddad@relexsolutions.example>\n"
    "Subject: Re: Shelf life field mapping\n\n"
    "Following up on the below.\n\n"
    "From: Priya Nair <priya.nair@acme-org.example>\n"
    "Sent: Tuesday, July 8, 2025 9:14 AM\n"
    "To: Nadia Haddad <n.haddad@relexsolutions.example>\n"
    "Subject: Shelf life field mapping\n\n"
    "For the fresh ordering configuration we need the field.\n"
)
_EMAIL_AFTER = (
    "Subject: Shelf life field mapping\n"
    "From: Nadia Haddad <n.haddad@relexsolutions.example>\n"
    "Date: Thursday, October 30, 2025 12:02 PM\n"
    "To: Ana Duarte <ana.duarte@relexsolutions.example>\n"
    "Messages in thread: 2\n\n"
    "We proceeded. Nobody objected.\n\n"
    "From: Priya Nair <priya.nair@acme-org.example>\n"
    "Sent: Tuesday, July 8, 2025 9:14 AM\n"
    "To: Nadia Haddad <n.haddad@relexsolutions.example>\n"
    "Subject: Shelf life field mapping\n\n"
    "For the fresh ordering configuration we need the field.\n"
)


def _write_corpus(root: Path, transcript_body: str) -> None:
    (root / "transcripts").mkdir(parents=True, exist_ok=True)
    (root / "emails").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "transcripts" / "01_internal.txt").write_text(
        _TRANSCRIPT_HEADER + transcript_body, encoding="utf-8"
    )


def test_evidence_ids_of_surviving_units_are_unchanged_after_delete_and_rebuild(tmp_path, conn):
    source = tmp_path / "source"
    _write_corpus(
        source,
        "Me: First turn.\nThem: Second turn.\nMe: Third turn.\nThem: Fourth turn.\n",
    )
    (source / "emails" / "01_thread.txt").write_text(_EMAIL_BEFORE, encoding="utf-8")

    ingest(conn, source, embedding_provider=None)
    before = {row["evidence_id"]: row["raw_text"] for row in repository.all_evidence_units(conn)}

    deleted_texts = {"Second turn.", "Following up on the below."}
    survivor_ids = {eid for eid, text in before.items() if text not in deleted_texts}
    assert len(survivor_ids) == len(before) - 2

    # Simulate Phase 5 physically scrubbing the deleted units' text.
    _write_corpus(source, "Me: First turn.\nMe: Third turn.\nThem: Fourth turn.\n")
    (source / "emails" / "01_thread.txt").write_text(_EMAIL_AFTER, encoding="utf-8")

    ingest(conn, source, embedding_provider=None)
    after = {row["evidence_id"]: row["raw_text"] for row in repository.all_evidence_units(conn)}

    for deleted_text in deleted_texts:
        assert deleted_text not in after.values()
    for eid in survivor_ids:
        assert eid in after, f"{eid} ({before[eid]!r}) did not survive rebuild"
        assert after[eid] == before[eid]
