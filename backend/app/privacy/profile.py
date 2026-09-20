"""Universal participant profile (AGENTS.md/CLAUDE.md 18.0.2).

Every participant -- ACTIVE or PSEUDONYMISED -- is DB-hydrated here from
the public relational graph and already-sanitized evidence rows. This
module never opens app/privacy/vault.py: a pseudonymised profile's history
is fully reconstructable from evidence_people + evidence_units alone,
because the canonical source was rewritten to the subject's own alias at
pseudonymisation time (CLAUDE.md 18.0.4) rather than the profile needing to
look anything up at read time.
"""

import json
import sqlite3
from dataclasses import dataclass, field

from app.db import repository


@dataclass
class ContributionEntry:
    evidence_id: str
    document_id: str
    document_type: str
    filename: str
    document_title: str | None
    relation: str
    event_date: str | None
    timestamp_text: str | None
    thread_context: str | None
    raw_text: str
    is_truncated: bool


@dataclass
class ProfileSummary:
    subject_id: str
    display_alias: str
    privacy_state: str
    display_name: str | None
    author_units: int
    speaker_units: int
    mentioned_units: int
    pseudonymised_at: str | None = None


@dataclass
class ProfileDetail(ProfileSummary):
    verification_result: dict | None = None
    history: list[ContributionEntry] = field(default_factory=list)


def _summary_row(row: sqlite3.Row) -> ProfileSummary:
    return ProfileSummary(
        subject_id=row["subject_id"],
        display_alias=row["display_alias"],
        privacy_state=row["privacy_state"],
        display_name=row["display_name"],
        author_units=0,
        speaker_units=0,
        mentioned_units=0,
        pseudonymised_at=row["pseudonymised_at"],
    )


def list_summaries(conn: sqlite3.Connection) -> list[ProfileSummary]:
    """Safe public summaries for the people list: an ACTIVE row's real name,
    a PSEUDONYMISED row's alias only, and contribution counts for both --
    never original PII for a pseudonymised subject."""
    rows = conn.execute(
        "SELECT subject_id, display_alias, privacy_state, display_name, pseudonymised_at "
        "FROM people ORDER BY COALESCE(display_name, display_alias)"
    ).fetchall()
    summaries = {row["subject_id"]: _summary_row(row) for row in rows}
    for row in conn.execute(
        "SELECT subject_id, relation, COUNT(DISTINCT evidence_id) AS n FROM evidence_people "
        "GROUP BY subject_id, relation"
    ):
        summary = summaries.get(row["subject_id"])
        if summary is None:
            continue
        field_name = {
            "AUTHOR": "author_units",
            "SPEAKER": "speaker_units",
            "MENTIONED": "mentioned_units",
        }[row["relation"]]
        setattr(summary, field_name, row["n"])
    return list(summaries.values())


def get_profile(conn: sqlite3.Connection, subject_id: str) -> ProfileDetail | None:
    """Complete history for one participant. Every Evidence Unit they
    authored, spoke, or were mentioned in, with the exact sanitized
    contribution text and source metadata -- DB-hydrated only, per
    CLAUDE.md 18.0.2 ('never requires a vault lookup')."""
    person = repository.get_person(conn, subject_id)
    if person is None:
        return None
    summary = _summary_row(person)
    for row in conn.execute(
        "SELECT relation, COUNT(DISTINCT evidence_id) AS n FROM evidence_people "
        "WHERE subject_id = ? GROUP BY relation",
        (subject_id,),
    ):
        field_name = {
            "AUTHOR": "author_units",
            "SPEAKER": "speaker_units",
            "MENTIONED": "mentioned_units",
        }[row["relation"]]
        setattr(summary, field_name, row["n"])

    verification_result = None
    if person["verification_result_json"]:
        try:
            verification_result = json.loads(person["verification_result_json"])
        except ValueError:
            verification_result = None

    history = [
        ContributionEntry(
            evidence_id=row["evidence_id"],
            document_id=row["document_id"],
            document_type=row["document_type"],
            filename=row["filename"],
            document_title=row["document_title"],
            relation=row["relation"],
            event_date=row["event_date"],
            timestamp_text=row["timestamp_text"],
            thread_context=row["thread_context"],
            raw_text=row["raw_text"],
            is_truncated=bool(row["is_truncated"]),
        )
        for row in repository.evidence_for_subject(conn, subject_id)
    ]

    return ProfileDetail(
        **summary.__dict__,
        verification_result=verification_result,
        history=history,
    )
