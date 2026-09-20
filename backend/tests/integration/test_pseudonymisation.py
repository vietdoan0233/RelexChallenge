"""Robust pseudonymisation end to end, on a synthetic corpus (Architecture
v1.6, AGENTS.md/CLAUDE.md 18.0). Supersedes test_privacy_purge.py: the old
generic-marker deletion contract is retired, not incrementally adapted.

Every test builds its own temporary source directory, database, ops
directory, and vault (CLAUDE.md 0.5) and never touches the repository's own
data/source, data/app.db, or data/private-vault.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.db import repository
from app.db.connection import connect
from app.ingestion.embeddings import MockEmbeddingProvider
from app.ingestion.service import ingest
from app.privacy import ops, profile, pseudonymise, reverse, vault
from app.privacy.gate import gate
from app.privacy.ops import PrivacyLockedError, PrivacyOperationError

TEAMS = (
    "Meeting: Weekly sync\nCustomer: Acme Org\nDate: 2024-07-09\nPhase: Implementation\n"
    "Attendees: Marco Rossi (RELEX), Kwame Boateng (RELEX), Lena Fischer (Acme)\n\n"
    "Marco Rossi\n0:050:05\nMR\nMarco Rossi 5 seconds\n"
    "Kwame will confirm the extract status after lunch.\n"
    "Kwame Boateng\n0:100:10\nKB\nKwame Boateng 10 seconds\n"
    "The extract completed and shelf life is populated on forty-eight percent.\n"
    "Lena Fischer\n0:150:15\nLF\nLena Fischer 15 seconds\n"
    "Thanks, moving on to ordering.\n"
)
INTERNAL = (
    "Meeting: Internal review\nCustomer: Acme Org\nDate: 2024-08-01\nPhase: Implementation\n"
    "Attendees: Marco Rossi (RELEX), Kwame Boateng (RELEX)\n\n"
    "Me: Kwame told me the extract succeeded.\n"
    "Them: Good, nothing else on that topic.\n"
)
EMAIL = (
    "Subject: Extract status\n"
    "From: Kwame Boateng <k.boateng@relexsolutions.example>\n"
    "Date: Thursday, October 30, 2025 12:02 PM\n"
    "To: Lena Fischer <lena.fischer@acme-org.example>; "
    "Kwame Boateng <k.boateng@relexsolutions.example>\n"
    "Messages in thread: 2\n\n"
    "Kwame is checking whether the field reached anything downstream.\n\n"
    "Kwame Boateng\nTechnical Consultant\n+44 7700 900 318\nk.boateng@relexsolutions.example\n\n"
    "From: Marco Rossi <marco.rossi@relexsolutions.example>\n"
    "Sent: Thursday, September 4, 2025 14:20\n"
    "To: Kwame Boateng <k.boateng@relexsolutions.example>\n"
    "Subject: Re: Extract status\n\n"
    "Please confirm the extract went out.\n"
)
REPORT = (
    "Subject: Weekly Acme update\n"
    "From: Marco Rossi <marco.rossi@relexsolutions.example>\n"
    "Date: Monday, April 6, 2026 17:30\n"
    "To: Lena Fischer <lena.fischer@acme-org.example>\n"
    "Messages in thread: 1\n\n"
    "Hi All,\n\n"
    "Topics worked on last week\n"
    "1.                  Q1 results compiled\n"
    "2.                  Kwame Boateng fixed the rounding defect\n"
    "3.                  Nightly article extract completed, no errors\n"
)
MANIFEST = {
    "description": "test",
    "entries": [
        {
            "canonical_name": "Kwame Boateng",
            "verified_aliases": [
                {"alias": "Kwame", "alias_type": "FIRST_NAME", "source_reference": "test"}
            ],
            "review_note": "Test reviewed short-form alias for the technical consultant.",
            "source_documents": ["transcripts/01_weekly-sync.txt"],
        }
    ],
}
NEEDLES = ["kwame", "boateng", "k.boateng@relexsolutions.example"]


class Instance:
    def __init__(self, root: Path):
        self.source = root / "source"
        self.db_path = root / "app.db"
        self.ops_dir = root / "privacy_ops"
        self.vault_path = root / "private-vault" / "vault.db.enc"
        self.vault_key = Fernet.generate_key().decode()
        self.artifacts = root / "artifacts"
        self.cache = root / "cache"
        for sub in ("transcripts", "emails", "reports"):
            (self.source / sub).mkdir(parents=True)
        for folder in (self.artifacts, self.cache):
            folder.mkdir()
        (self.source / "transcripts" / "01_weekly-sync.txt").write_text(TEAMS, encoding="utf-8")
        (self.source / "transcripts" / "02_INTERNAL-review.txt").write_text(
            INTERNAL, encoding="utf-8"
        )
        (self.source / "emails" / "01_extract-status.txt").write_text(EMAIL, encoding="utf-8")
        (self.source / "reports" / "01_weekly-report.txt").write_text(REPORT, encoding="utf-8")
        (self.source / "reviewed_identities.json").write_text(
            json.dumps(MANIFEST), encoding="utf-8"
        )
        self.provider = MockEmbeddingProvider()
        self.conn = connect(str(self.db_path))
        ingest(self.conn, self.source, self.provider)
        # Derived artifacts/cache that contain the name must be scrubbed too.
        (self.artifacts / "export.json").write_text('{"who": "Kwame Boateng"}', encoding="utf-8")
        (self.cache / "tmp.txt").write_text("k.boateng@relexsolutions.example", encoding="utf-8")

    def subject_id_for(self, display_name: str) -> str:
        subject_id = repository.find_subject_id_by_structural_name(self.conn, display_name)
        assert subject_id is not None, f"no subject for {display_name!r}"
        return subject_id

    def pseudonymise(self, subject_id=None, provider="default", **kwargs):
        if subject_id is None:
            subject_id = self.subject_id_for("Kwame Boateng")
        return pseudonymise.pseudonymise(
            self.conn,
            source_dir=self.source,
            db_path=self.db_path,
            ops_dir=self.ops_dir,
            vault_path=self.vault_path,
            vault_key=self.vault_key,
            subject_id=subject_id,
            artifact_dirs=[self.artifacts, self.cache],
            provider=self.provider if provider == "default" else provider,
            **kwargs,
        )

    def reverse(self, subject_id, provider="default", confirm=True):
        return reverse.reverse_pseudonymisation(
            self.conn,
            source_dir=self.source,
            db_path=self.db_path,
            ops_dir=self.ops_dir,
            vault_path=self.vault_path,
            vault_key=self.vault_key,
            subject_id=subject_id,
            confirm=confirm,
            artifact_dirs=[self.artifacts, self.cache],
            provider=self.provider if provider == "default" else provider,
        )

    def ids(self):
        return {r[0] for r in self.conn.execute("SELECT evidence_id FROM evidence_units")}

    def units(self):
        return {r["evidence_id"]: r for r in self.conn.execute("SELECT * FROM evidence_units")}

    def all_source_text(self):
        return "\n".join(
            p.read_text(encoding="utf-8") for p in self.source.rglob("*") if p.is_file()
        )


@pytest.fixture
def inst(tmp_path):
    instance = Instance(tmp_path)
    yield instance
    instance.conn.close()


def _add_case(conn, case_id, query, evidence_ids, prose=""):
    conn.execute(
        "INSERT INTO cases VALUES (?, ?, ?, 't', 't')",
        (case_id, query, json.dumps({"answer_summary": prose})),
    )
    for evidence_id in evidence_ids:
        conn.execute("INSERT INTO case_evidence VALUES (?, ?, 'SUPPORT')", (case_id, evidence_id))
    conn.commit()


# -------------------------------------------------------------- identity


def test_setup_sees_the_person_and_the_reviewed_short_alias(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    aliases = {
        r[0]
        for r in inst.conn.execute(
            "SELECT alias FROM person_aliases WHERE subject_id = ?", (subject_id,)
        )
    }
    assert {"Kwame Boateng", "Kwame", "k.boateng@relexsolutions.example"} <= aliases


def test_subject_id_is_a_random_uuid_never_name_derived(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", subject_id)
    assert "kwame" not in subject_id.lower()
    assert "boateng" not in subject_id.lower()


def test_every_active_subject_already_has_a_stable_display_alias(inst):
    """Architecture v1.6: display_alias exists from creation for every
    subject, active or not -- pseudonymisation switches which fields are
    public, it does not mint the alias at that moment."""
    rows = inst.conn.execute("SELECT display_alias, privacy_state FROM people").fetchall()
    assert rows
    for row in rows:
        assert row["privacy_state"] == "ACTIVE"
        assert re.fullmatch(r"Participant [A-Z0-9]{4}-[A-Z0-9]{2}", row["display_alias"])


def test_display_aliases_are_distinct_and_never_name_derived_across_five_subjects(inst, tmp_path):
    """AGENTS.md 23: aliases are distinct across at least five structurally
    different targets and never use names, hashes, initials, or sequences."""
    # Marco Rossi/Kwame Boateng/Lena Fischer already exist from ingestion.
    # Two more structurally different targets: a text-only reviewed identity
    # and a fresh email-only sender, added to reach five.
    extra_names = [
        ("11111111-1111-4111-8111-111111111111", "Nils Ackermann"),
        ("22222222-2222-4222-8222-222222222222", "Tobias Ekström"),
    ]
    for subject_id, name in extra_names:
        alias = repository.generate_unique_display_alias(inst.conn)
        inst.conn.execute(
            "INSERT INTO people (subject_id, display_alias, privacy_state, display_name) "
            "VALUES (?, ?, 'ACTIVE', ?)",
            (subject_id, alias, name),
        )
    inst.conn.commit()
    rows = inst.conn.execute("SELECT display_name, display_alias FROM people").fetchall()
    by_name = {r["display_name"]: r["display_alias"] for r in rows}
    aliases = list(by_name.values())
    assert len(aliases) >= 5
    assert len(set(aliases)) == len(aliases), "every alias must be distinct"
    for name, alias in by_name.items():
        first, last = name.split()[0].lower(), name.split()[-1].lower()
        initials = "".join(w[0] for w in name.split()).lower()
        assert first not in alias.lower()
        assert last not in alias.lower()
        assert initials not in alias.lower().replace("participant ", "").replace("-", "")


def test_alias_collision_retries_generation_never_increments_a_counter(inst, monkeypatch):
    calls = {"n": 0}
    real_generate = repository.generate_display_alias

    def flaky():
        calls["n"] += 1
        return "Participant AAAA-AA" if calls["n"] == 1 else real_generate()

    # Occupy the first candidate so generate_unique_display_alias must retry.
    inst.conn.execute(
        "INSERT INTO people (subject_id, display_alias, privacy_state, display_name) "
        "VALUES ('33333333-3333-4333-8333-333333333333', 'Participant AAAA-AA', 'ACTIVE', 'X')"
    )
    inst.conn.commit()
    monkeypatch.setattr(repository, "generate_display_alias", flaky)
    alias = repository.generate_unique_display_alias(inst.conn)
    assert alias != "Participant AAAA-AA"
    assert calls["n"] >= 2


def test_a_known_display_alias_is_never_treated_as_a_new_person(inst):
    """CLAUDE.md 18.0: 'never treat Participant Q7M4-N8 as a new real
    person'. Simulates the post-pseudonymisation trace by inserting an
    alias-bearing structural name directly, without going through a real
    pseudonymisation operation."""
    from app.ingestion import people as people_module
    from app.ingestion.models import ParsedDocument, ParsedUnit

    alias = repository.generate_unique_display_alias(inst.conn)
    subject_id = "44444444-4444-4444-8444-444444444444"
    inst.conn.execute(
        "INSERT INTO people (subject_id, display_alias, privacy_state, display_name) "
        "VALUES (?, ?, 'PSEUDONYMISED', NULL)",
        (subject_id, alias),
    )
    inst.conn.commit()
    before = repository.people_row_count(inst.conn)

    docs = [
        ParsedDocument(
            document_id="doc-alias",
            filename="doc-alias.txt",
            document_type="TRANSCRIPT",
            title=None,
            source_date=None,
            thread_context=None,
            units=[ParsedUnit(raw_text="Fine by me.", speaker_sender=alias)],
            attendees=[alias],
        )
    ]
    people_module.seed_and_discover(inst.conn, docs, inst.source)
    assert repository.people_row_count(inst.conn) == before
    assert repository.find_subject_id_by_structural_name(inst.conn, alias) == subject_id


# ---------------------------------------------------------------- preview


def test_preview_reports_counts_without_changing_anything(inst):
    before = inst.all_source_text()
    subject_id = inst.subject_id_for("Kwame Boateng")
    result = pseudonymise.preview(inst.conn, inst.source, subject_id)
    assert result.speaker_units >= 1 and result.units_to_rewrite >= 4
    assert result.files_to_rewrite == 5  # 4 evidence files + the reviewed manifest
    assert result.display_alias
    assert inst.all_source_text() == before
    unknown = "00000000-0000-4000-8000-000000000000"
    assert pseudonymise.preview(inst.conn, inst.source, unknown) is None


# ------------------------------------------------------------ pseudonymise


def test_pseudonymise_rewrites_every_tracked_identifier_to_the_alias(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    result = inst.pseudonymise(subject_id)
    assert result.verified and all(v == 0 for v in result.verification.values())
    assert all(result.checks.values())
    assert result.privacy_state == "PSEUDONYMISED"

    # Independent of the service's own verifier.
    from app.privacy import verify

    assert verify.scan_files(inst.source, NEEDLES) == 0
    assert verify.scan_files(inst.artifacts, NEEDLES) == 0
    assert verify.scan_files(inst.cache, NEEDLES) == 0
    conn = sqlite3.connect(inst.db_path)
    conn.row_factory = sqlite3.Row
    assert verify.scan_database_rows(conn, NEEDLES) == 0
    conn.close()
    assert verify.scan_database_files(inst.db_path, NEEDLES) == 0

    row = repository.get_person(inst.conn, subject_id)
    assert row["privacy_state"] == "PSEUDONYMISED"
    assert row["display_name"] is None
    assert row["display_alias"] == result.display_alias


def test_participant_row_and_relationships_are_never_deleted(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    before_relations = {
        (r["evidence_id"], r["relation"])
        for r in inst.conn.execute(
            "SELECT evidence_id, relation FROM evidence_people WHERE subject_id = ?", (subject_id,)
        )
    }
    assert before_relations
    inst.pseudonymise(subject_id)
    assert repository.get_person(inst.conn, subject_id) is not None
    after_relations = {
        (r["evidence_id"], r["relation"])
        for r in inst.conn.execute(
            "SELECT evidence_id, relation FROM evidence_people WHERE subject_id = ?", (subject_id,)
        )
    }
    assert before_relations <= after_relations


def test_structural_metadata_is_rewritten_not_just_body_text(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    result = inst.pseudonymise(subject_id)
    alias = result.display_alias
    teams = (inst.source / "transcripts" / "01_weekly-sync.txt").read_text(encoding="utf-8")
    assert f"Attendees: Marco Rossi (RELEX), {alias} (RELEX), Lena Fischer (Acme)" in teams
    assert "\nKB\n" not in teams  # initials chrome
    assert f"{alias} 10 seconds" in teams
    email = (inst.source / "emails" / "01_extract-status.txt").read_text(encoding="utf-8")
    assert f"From: {alias} <" in email
    assert "@pseudonymised.invalid" in email
    assert "+44 7700 900 318" not in email  # signature block removed with the name
    assert "Technical Consultant" not in email
    assert "lena.fischer@acme-org.example" in email  # other people are untouched


def test_organizational_evidence_survives_pseudonymised_and_retrievable(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    result = inst.pseudonymise(subject_id)
    alias = result.display_alias
    texts = " || ".join(r["raw_text"] for r in inst.units().values())
    assert "shelf life is populated on forty-eight percent" in texts
    assert "the extract succeeded" in texts.lower() or "extract succeeded" in texts
    speakers = {r["speaker_sender"] for r in inst.units().values()}
    assert alias in speakers
    hit = inst.conn.execute(
        "SELECT evidence_id FROM evidence_fts WHERE evidence_fts MATCH 'forty'"
    ).fetchall()
    assert hit


def test_every_evidence_id_is_stable_across_the_operation(inst):
    before = inst.ids()
    inst.pseudonymise()
    assert inst.ids() == before


def test_a_rebuild_after_pseudonymisation_does_not_resurrect_the_original_identity(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    result = inst.pseudonymise(subject_id)
    ids = inst.ids()
    ingest(inst.conn, inst.source, inst.provider)  # the normal rebuild command
    assert inst.ids() == ids

    from app.privacy import verify

    assert verify.scan_database_rows(inst.conn, NEEDLES) == 0
    assert verify.scan_files(inst.source, NEEDLES) == 0
    row = repository.get_person(inst.conn, subject_id)
    assert row["privacy_state"] == "PSEUDONYMISED"
    assert row["display_alias"] == result.display_alias
    # The subject/profile graph -- not just the row -- must survive the rebuild.
    detail = profile.get_profile(inst.conn, subject_id)
    assert detail is not None
    assert len(detail.history) >= 4


def test_two_subjects_can_be_pseudonymised_one_after_the_other_with_distinct_aliases(inst):
    ids = inst.ids()
    kwame_id = inst.subject_id_for("Kwame Boateng")
    marco_id = inst.subject_id_for("Marco Rossi")
    lena_id = inst.subject_id_for("Lena Fischer")
    first = inst.pseudonymise(kwame_id)
    second = inst.pseudonymise(marco_id)
    assert first.display_alias != second.display_alias
    assert inst.ids() == ids

    from app.privacy import verify

    assert verify.scan_files(inst.source, NEEDLES + ["marco rossi", "marco.rossi@"]) == 0
    row_marco = repository.get_person(inst.conn, marco_id)
    assert row_marco["privacy_state"] == "PSEUDONYMISED"
    # The untouched third person is unaffected and still distinguishable.
    row_lena = repository.get_person(inst.conn, lena_id)
    assert row_lena["privacy_state"] == "ACTIVE"
    assert row_lena["display_name"] == "Lena Fischer"
    text = inst.all_source_text()
    assert first.display_alias in text and second.display_alias in text
    assert first.display_alias != second.display_alias


def test_group_boundaries_are_backfilled_for_a_database_that_predates_them(inst):
    ids = inst.ids()
    inst.conn.execute("UPDATE source_locators SET starts_group = NULL")
    inst.conn.commit()
    kwame_id = inst.subject_id_for("Kwame Boateng")
    marco_id = inst.subject_id_for("Marco Rossi")
    inst.pseudonymise(kwame_id)
    inst.pseudonymise(marco_id)
    # Two different pseudonymised speakers are adjacent in the weekly-sync
    # transcript; their turns must not fuse and no Evidence ID may disappear.
    assert inst.ids() == ids
    speakers = [
        r["speaker_sender"]
        for r in inst.conn.execute(
            "SELECT speaker_sender FROM evidence_units WHERE document_id = '01_weekly-sync' "
            "ORDER BY unit_index"
        )
    ]
    assert len({s for s in speakers if s and s.startswith("Participant")}) == 2


def test_reviewed_identity_manifest_entry_is_removed(inst):
    inst.pseudonymise()
    data = json.loads((inst.source / "reviewed_identities.json").read_text(encoding="utf-8"))
    assert data["entries"] == []


def test_a_unique_first_name_is_rewritten_with_the_full_name_even_if_never_reviewed(tmp_path):
    """ "Kwame Boateng" and "Kwame" are one participant: with no reviewed alias at all, the
    strict first-name basis still rewrites the bare first name because nobody else has it."""
    instance = Instance(tmp_path)
    (instance.source / "reviewed_identities.json").write_text(
        json.dumps({"description": "x", "entries": []}), encoding="utf-8"
    )
    ingest(instance.conn, instance.source, instance.provider)
    subject_id = instance.subject_id_for("Kwame Boateng")

    preview = pseudonymise.preview(instance.conn, instance.source, subject_id)
    assert preview is not None and preview.first_name == "Kwame"
    assert preview.unassigned_first_name is None

    result = instance.pseudonymise()

    email = (instance.source / "emails" / "01_extract-status.txt").read_text(encoding="utf-8")
    assert "Kwame" not in email and "Boateng" not in email
    assert f"{result.display_alias} is checking" in email
    assert result.verified
    from app.privacy import verify

    assert verify.scan_files(instance.source, NEEDLES) == 0
    instance.conn.close()


def test_a_pseudonymised_first_name_survives_the_vault_round_trip(tmp_path):
    """The first-name basis rides in the vault bundle like any other alias, so an admin
    reversal verifies cleanly and the original identity is attributable again. (Reversal
    restores every occurrence to the vault's one canonical name; it cannot know which short
    form stood at each position -- the documented, non-guessing limitation.)"""
    instance = Instance(tmp_path)
    (instance.source / "reviewed_identities.json").write_text(
        json.dumps({"description": "x", "entries": []}), encoding="utf-8"
    )
    ingest(instance.conn, instance.source, instance.provider)
    subject_id = instance.subject_id_for("Kwame Boateng")
    done = instance.pseudonymise()
    assert done.verified

    reversed_result = instance.reverse(subject_id)

    assert reversed_result.verified
    email = (instance.source / "emails" / "01_extract-status.txt").read_text(encoding="utf-8")
    assert done.display_alias not in email and "Kwame Boateng" in email
    assert (
        instance.conn.execute(
            "SELECT privacy_state FROM people WHERE subject_id = ?", (subject_id,)
        ).fetchone()["privacy_state"]
        == "ACTIVE"
    )
    instance.conn.close()


def test_a_short_first_name_inside_other_words_does_not_fail_verification(tmp_path):
    """ "Ana" is a substring of "management" and "analysis". The rewrite only touches the whole
    token, so the verifier must also judge it as a whole token: otherwise every short first name
    fail-closes forever on innocent words. A real surviving "Ana" is still a leak."""
    instance = Instance(tmp_path)
    (instance.source / "reviewed_identities.json").write_text(
        json.dumps({"description": "x", "entries": []}), encoding="utf-8"
    )
    (instance.source / "emails" / "02_data-report.txt").write_text(
        "Subject: Analysis of management data\n"
        "From: Ana Souza <ana.souza@acme-org.example>\n"
        "Date: Friday, October 31, 2025 09:00 AM\n"
        "To: Lena Fischer <lena.fischer@acme-org.example>\n"
        "Messages in thread: 1\n\n"
        "The analysis of the management banana report is attached. Ana will present it.\n",
        encoding="utf-8",
    )
    ingest(instance.conn, instance.source, instance.provider)
    subject_id = instance.subject_id_for("Ana Souza")

    result = instance.pseudonymise(subject_id)

    assert result.verified, result.verification
    text = (instance.source / "emails" / "02_data-report.txt").read_text(encoding="utf-8")
    assert "analysis of the management banana report" in text  # innocent words untouched
    assert f"{result.display_alias} will present it" in text  # the bare first name went with her
    assert "Ana Souza" not in text and "Ana will" not in text
    instance.conn.close()


def test_a_first_name_shared_by_two_participants_is_never_guessed(tmp_path):
    """A bare "Kwame" could be either Kwame: it must be left alone, and the console must be
    able to say so. The full name is still rewritten."""
    instance = Instance(tmp_path)
    (instance.source / "reviewed_identities.json").write_text(
        json.dumps({"description": "x", "entries": []}), encoding="utf-8"
    )
    (instance.source / "emails" / "02_second-kwame.txt").write_text(
        "Subject: Access list\n"
        "From: Kwame Mensah <k.mensah@acme-org.example>\n"
        "Date: Friday, October 31, 2025 09:00 AM\n"
        "To: Lena Fischer <lena.fischer@acme-org.example>\n"
        "Messages in thread: 1\n\n"
        "Access list attached.\n",
        encoding="utf-8",
    )
    ingest(instance.conn, instance.source, instance.provider)
    subject_id = instance.subject_id_for("Kwame Boateng")

    preview = pseudonymise.preview(instance.conn, instance.source, subject_id)
    assert preview is not None
    assert preview.first_name is None
    assert (preview.unassigned_first_name, preview.unassigned_reason) == ("Kwame", "shared")

    result = instance.pseudonymise()

    email = (instance.source / "emails" / "01_extract-status.txt").read_text(encoding="utf-8")
    assert "Kwame Boateng" not in email and "Boateng" not in email
    assert "Kwame is checking" in email  # ambiguous: deliberately untouched
    assert result.verified
    instance.conn.close()


def test_reviewed_spoken_employee_number_is_rewritten_with_the_person(inst):
    """An employee number spoken in words identifies a person as directly as a name;
    once a reviewer lists it as a variant of that person it goes with them."""
    kickoff = inst.source / "transcripts" / "03_kickoff.txt"
    kickoff.write_text(
        "Meeting: Kickoff\nCustomer: Acme Org\nDate: 2024-07-15\nPhase: Implementation\n"
        "Attendees: Marco Rossi (RELEX), Lena Fischer (Acme)\n\n"
        "Marco Rossi\n0:050:05\nMR\nMarco Rossi 5 seconds\n"
        "For the access list, Kwame is five one oh three, if your system wants that.\n",
        encoding="utf-8",
    )
    manifest = json.loads((inst.source / "reviewed_identities.json").read_text(encoding="utf-8"))
    manifest["entries"][0]["verified_aliases"].append(
        {"alias": "five one oh three", "alias_type": "VARIANT", "source_reference": "test"}
    )
    (inst.source / "reviewed_identities.json").write_text(json.dumps(manifest), encoding="utf-8")
    ingest(inst.conn, inst.source, inst.provider)

    result = inst.pseudonymise()

    assert result.verified
    text = kickoff.read_text(encoding="utf-8")
    assert "five one oh three" not in text and "Kwame" not in text
    assert "if your system wants that" in text  # the non-personal remainder survives

    from app.privacy import verify

    assert verify.scan_files(inst.source, [*NEEDLES, "five one oh three"]) == 0
    assert verify.scan_database_files(inst.db_path, [*NEEDLES, "five one oh three"]) == 0


# ------------------------------------------------------- embeddings


def test_unchanged_embeddings_are_kept_and_changed_ones_regenerated_from_alias_text(inst):
    old = {
        r[0]: r[1]
        for r in inst.conn.execute("SELECT evidence_id, vector_json FROM evidence_embeddings")
    }
    units_before = {i: r["raw_text"] for i, r in inst.units().items()}
    result = inst.pseudonymise()
    new = {
        r[0]: r[1]
        for r in inst.conn.execute("SELECT evidence_id, vector_json FROM evidence_embeddings")
    }
    units_after = {i: r["raw_text"] for i, r in inst.units().items()}

    assert set(new) == set(units_after)  # every unit has an embedding again
    changed = {i for i in units_after if units_after[i] != units_before[i]}
    assert changed and result.embeddings_regenerated == len(changed)
    for evidence_id in units_after:
        if evidence_id in changed:
            expected = json.dumps(inst.provider.embed_batch([units_after[evidence_id]])[0])
            assert new[evidence_id] == expected  # of the alias-bearing text, not the old
            assert new[evidence_id] != old[evidence_id]
        else:
            assert new[evidence_id] == old[evidence_id]


def test_without_a_provider_no_stale_embedding_survives_and_degradation_is_reported(inst):
    changed_before = {
        i for i, r in inst.units().items() if re.search(r"kwame", r["raw_text"], re.IGNORECASE)
    }
    result = inst.pseudonymise(provider=None)
    assert result.embeddings_regenerated == 0
    assert result.embeddings_pending >= len(changed_before) > 0
    present = {r[0] for r in inst.conn.execute("SELECT evidence_id FROM evidence_embeddings")}
    assert not (present & changed_before)  # old vectors of changed text are gone


# ---------------------------------------------------------- dependencies


def test_dependent_cases_are_invalidated_and_unrelated_ones_kept(inst):
    affected = next(i for i, r in inst.units().items() if "Kwame" in r["raw_text"])
    unrelated = next(
        i
        for i, r in inst.units().items()
        if "Kwame" not in r["raw_text"] and r["speaker_sender"] == "Lena Fischer"
    )
    _add_case(inst.conn, "c-cites", "q1", [affected])
    _add_case(inst.conn, "c-prose", "What did Kwame Boateng say?", [unrelated], "Kwame said so.")
    _add_case(inst.conn, "c-clean", "Ordering?", [unrelated], "Ordering was discussed.")
    result = inst.pseudonymise()
    remaining = {r[0] for r in inst.conn.execute("SELECT case_id FROM cases")}
    assert remaining == {"c-clean"} and result.cases_invalidated == 2
    assert (
        inst.conn.execute(
            "SELECT COUNT(*) FROM case_evidence WHERE case_id IN ('c-cites','c-prose')"
        ).fetchone()[0]
        == 0
    )


def test_the_lock_is_released_and_the_ops_folder_left_empty(inst):
    inst.pseudonymise()
    assert not ops.is_locked(inst.ops_dir)
    assert list(inst.ops_dir.iterdir()) == []


def test_pseudonymise_of_an_unknown_subject_fails_before_locking(inst):
    with pytest.raises(PrivacyOperationError):
        inst.pseudonymise(subject_id="00000000-0000-4000-8000-000000000000")
    assert not ops.is_locked(inst.ops_dir)


def test_pseudonymise_of_an_already_pseudonymised_subject_fails_before_locking(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    with pytest.raises(PrivacyOperationError):
        inst.pseudonymise(subject_id)
    assert not ops.is_locked(inst.ops_dir)


# ------------------------------------------------- locking and recovery


def test_a_failed_operation_stays_locked_and_never_reports_success(inst, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("k.boateng@relexsolutions.example detail that must not leak")

    monkeypatch.setattr(pseudonymise, "_rebuild_from_rewritten_source", boom)
    with pytest.raises(PrivacyOperationError) as info:
        inst.pseudonymise()
    assert "boateng" not in str(info.value).lower()
    assert ops.is_locked(inst.ops_dir)
    with pytest.raises(PrivacyLockedError):
        ops.assert_unlocked(inst.ops_dir)
    with pytest.raises(PrivacyLockedError):
        inst.pseudonymise()  # a second operation cannot start


def test_interrupted_operation_resumes_to_completion(inst, monkeypatch):
    original = pseudonymise._rebuild_from_rewritten_source
    monkeypatch.setattr(
        pseudonymise,
        "_rebuild_from_rewritten_source",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash")),
    )
    with pytest.raises(PrivacyOperationError):
        inst.pseudonymise()
    assert ops.read_lock(inst.ops_dir)["state"] == ops.SOURCE_DONE
    # Source was already rewritten before the crash.

    from app.privacy import verify

    assert verify.scan_files(inst.source, NEEDLES) == 0

    monkeypatch.setattr(pseudonymise, "_rebuild_from_rewritten_source", original)
    inst.conn.close()
    outcome = pseudonymise.recover(
        source_dir=inst.source,
        db_path=inst.db_path,
        ops_dir=inst.ops_dir,
        vault_path=inst.vault_path,
        vault_key=inst.vault_key,
        artifact_dirs=[inst.artifacts, inst.cache],
        provider=inst.provider,
    )
    assert outcome == "resumed"
    assert not ops.is_locked(inst.ops_dir) and list(inst.ops_dir.iterdir()) == []
    conn = connect(str(inst.db_path))
    assert verify.scan_database_rows(conn, NEEDLES) == 0
    assert verify.scan_database_files(inst.db_path, NEEDLES) == 0
    conn.close()
    inst.conn = connect(str(inst.db_path))


def test_orphan_planning_lock_with_no_plan_is_cleared_safely(tmp_path):
    ops_dir = tmp_path / "ops"
    ops.acquire(ops_dir, "op1")
    outcome = pseudonymise.recover(
        source_dir=tmp_path,
        db_path=tmp_path / "x.db",
        ops_dir=ops_dir,
        vault_path=tmp_path / "vault.db.enc",
        vault_key=Fernet.generate_key().decode(),
    )
    assert outcome == "cleared orphan lock"
    assert not ops.is_locked(ops_dir)


def test_finalizing_with_the_plan_already_removed_is_finished_not_treated_as_corruption(tmp_path):
    ops_dir = tmp_path / "ops"
    ops.acquire(ops_dir, "op1")
    ops.set_state(ops_dir, ops.FINALIZING)
    outcome = pseudonymise.recover(
        source_dir=tmp_path,
        db_path=tmp_path / "x.db",
        ops_dir=ops_dir,
        vault_path=tmp_path / "vault.db.enc",
        vault_key=Fernet.generate_key().decode(),
    )
    assert outcome == "finalized"
    assert not ops.is_locked(ops_dir)


@pytest.mark.parametrize("state", [ops.SOURCE_IN_PROGRESS, ops.DB_DONE, "CORRUPT", "WHAT"])
def test_any_other_shape_without_a_readable_plan_fails_closed(tmp_path, state):
    ops_dir = tmp_path / "ops"
    ops.acquire(ops_dir, "op1")
    ops.set_state(ops_dir, state)
    with pytest.raises(PrivacyOperationError):
        pseudonymise.recover(
            source_dir=tmp_path,
            db_path=tmp_path / "x.db",
            ops_dir=ops_dir,
            vault_path=tmp_path / "vault.db.enc",
            vault_key=Fernet.generate_key().decode(),
        )
    assert ops.is_locked(ops_dir)


def test_a_torn_plan_file_fails_closed(tmp_path):
    ops_dir = tmp_path / "ops"
    ops.acquire(ops_dir, "op1")
    ops.set_state(ops_dir, ops.SOURCE_DONE)
    (ops_dir / ops.PLAN_NAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(PrivacyOperationError):
        pseudonymise.recover(
            source_dir=tmp_path,
            db_path=tmp_path / "x.db",
            ops_dir=ops_dir,
            vault_path=tmp_path / "vault.db.enc",
            vault_key=Fernet.generate_key().decode(),
        )
    assert ops.is_locked(ops_dir)


def test_atomic_write_never_leaves_a_torn_file(tmp_path):
    target = tmp_path / "f.txt"
    ops.atomic_write(target, "one")
    ops.atomic_write(target, "two")
    assert target.read_text() == "two"
    assert [p.name for p in tmp_path.iterdir()] == ["f.txt"]


def test_verification_failure_keeps_the_system_locked(inst, monkeypatch):
    from app.privacy import verify as verify_module

    real = verify_module.verify

    def leaky(**kwargs):
        report = real(**kwargs)
        report.counts["source_files"] = 3
        return report

    monkeypatch.setattr(verify_module, "verify", leaky)
    with pytest.raises(PrivacyOperationError):
        inst.pseudonymise()
    assert ops.is_locked(inst.ops_dir)


def test_no_staging_table_survives_a_completed_operation(inst):
    inst.pseudonymise()
    tables = {r[0] for r in inst.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "privacy_embedding_stash" not in tables


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX permission bits are not meaningful on Windows/NTFS"
)
def test_plan_and_lock_are_private_to_the_owner(inst, monkeypatch):
    seen = {}
    real = pseudonymise._rebuild_from_rewritten_source

    def peek(*args, **kwargs):
        seen["dir"] = inst.ops_dir.stat().st_mode & 0o777
        seen["plan"] = (inst.ops_dir / ops.PLAN_NAME).stat().st_mode & 0o777
        return real(*args, **kwargs)

    monkeypatch.setattr(pseudonymise, "_rebuild_from_rewritten_source", peek)
    inst.pseudonymise()
    assert seen["dir"] == 0o700 and seen["plan"] == 0o600


def test_plan_never_contains_the_original_name_email_or_alias(inst, monkeypatch):
    """AGENTS.md 18.0.5: the plan may contain IDs, paths, and already-alias-
    bearing replacement content, but never the original name/email/alias."""
    captured = {}
    real_write_plan = ops.write_plan

    def capture(ops_dir, plan):
        captured["plan"] = json.loads(json.dumps(plan))
        return real_write_plan(ops_dir, plan)

    monkeypatch.setattr(ops, "write_plan", capture)
    inst.pseudonymise()
    blob = json.dumps(captured["plan"]).lower()
    assert "kwame" not in blob
    assert "boateng" not in blob
    assert "k.boateng@relexsolutions.example" not in blob


def test_windows_style_backslash_paths_in_a_legacy_plan_are_normalized(inst):
    """AGENTS.md: 'Use POSIX separators... safely normalize legacy Windows
    separators'. A plan is always written with as_posix() keys now, but
    recovery must still tolerate a pre-fix plan that used backslashes."""
    subject_id = inst.subject_id_for("Kwame Boateng")
    from app.privacy import targets

    target = targets.resolve_active_target(inst.conn, subject_id)
    files = pseudonymise._rewrite_all(inst.source, target)
    assert all("\\" not in key for key in files), "keys must always be POSIX-separated"
    # A legacy plan with backslash-separated keys must still resolve to the
    # same file when normalized the same way _run defensively normalizes it.
    legacy_key = next(iter(files)).replace("/", "\\")
    normalized = legacy_key.replace("\\", "/")
    assert normalized in files


# ----------------------------------------------------------------- vault


def test_vault_stores_ciphertext_only_no_plaintext_original_name(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    raw = inst.vault_path.read_bytes()
    assert b"Kwame" not in raw
    assert b"Boateng" not in raw
    assert b"k.boateng" not in raw


def test_vault_roundtrips_the_identity_bundle(tmp_path):
    key = Fernet.generate_key().decode()
    vault_path = tmp_path / "vault.db.enc"
    bundle = vault.IdentityBundle(
        original_name="Kwame Boateng",
        original_emails=("k.boateng@relexsolutions.example",),
        original_aliases=("Kwame",),
    )
    vault.store_identity(vault_path, key, "subject-1", bundle)
    back = vault.retrieve_identity(vault_path, key, "subject-1")
    assert back == bundle


def test_missing_vault_key_fails_closed_on_store(tmp_path):
    with pytest.raises(vault.VaultConfigError):
        vault.store_identity(
            tmp_path / "vault.db.enc", "", "subject-1", vault.IdentityBundle(original_name="X")
        )


def test_missing_vault_key_fails_closed_on_retrieve(tmp_path):
    with pytest.raises(vault.VaultConfigError):
        vault.retrieve_identity(tmp_path / "vault.db.enc", "", "subject-1")


def test_wrong_vault_key_cannot_decrypt(tmp_path):
    vault_path = tmp_path / "vault.db.enc"
    vault.store_identity(
        vault_path,
        Fernet.generate_key().decode(),
        "subject-1",
        vault.IdentityBundle(original_name="Kwame Boateng"),
    )
    with pytest.raises(vault.VaultError):
        vault.retrieve_identity(vault_path, Fernet.generate_key().decode(), "subject-1")


def test_standard_connection_to_the_main_database_has_no_vault_table(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    tables = {r[0] for r in inst.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "vault_entries" not in tables


def test_pseudonymisation_operation_id_is_never_the_original_name(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    result = inst.pseudonymise(subject_id)
    assert "kwame" not in result.operation_id.lower()
    row = inst.conn.execute(
        "SELECT * FROM privacy_operations WHERE subject_id = ?", (subject_id,)
    ).fetchone()
    assert row is not None
    blob = json.dumps(dict(row)).lower()
    assert "kwame" not in blob and "boateng" not in blob


# ------------------------------------------------------------ profiles


def test_profile_history_includes_every_contribution_after_pseudonymisation(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    before = profile.get_profile(inst.conn, subject_id)
    assert before is not None
    before_ids = {h.evidence_id for h in before.history}

    inst.pseudonymise(subject_id)
    after = profile.get_profile(inst.conn, subject_id)
    assert after.privacy_state == "PSEUDONYMISED"
    assert after.display_name is None
    after_ids = {h.evidence_id for h in after.history}
    assert before_ids <= after_ids
    assert any(h.raw_text for h in after.history)
    assert all(after.display_alias not in "" for h in after.history)  # sanity: no crash


def test_active_profile_shows_real_name_pseudonymised_profile_does_not(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    active = profile.get_profile(inst.conn, subject_id)
    assert active.display_name == "Kwame Boateng"

    inst.pseudonymise(subject_id)
    pseudonymised = profile.get_profile(inst.conn, subject_id)
    assert pseudonymised.display_name is None
    assert "Kwame" not in json.dumps(pseudonymised.__dict__, default=lambda o: o.__dict__)


def test_two_pseudonymised_profiles_remain_distinguishable(inst):
    kwame_id = inst.subject_id_for("Kwame Boateng")
    marco_id = inst.subject_id_for("Marco Rossi")
    inst.pseudonymise(kwame_id)
    inst.pseudonymise(marco_id)
    kwame_profile = profile.get_profile(inst.conn, kwame_id)
    marco_profile = profile.get_profile(inst.conn, marco_id)
    assert kwame_profile.display_alias != marco_profile.display_alias
    assert {h.evidence_id for h in kwame_profile.history} != {
        h.evidence_id for h in marco_profile.history
    }


def test_get_profile_never_touches_the_vault_module(inst, monkeypatch):
    # pseudonymise() itself legitimately calls vault.retrieve_identity (see
    # its module docstring: rebuilding the verification needle list), so the
    # patch must only take effect *after* that operation has completed --
    # this test isolates app.privacy.profile specifically.
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)

    import app.privacy.vault as vault_module

    def boom(*a, **k):
        raise AssertionError("profile.get_profile must never call the vault")

    monkeypatch.setattr(vault_module, "retrieve_identity", boom)
    detail = profile.get_profile(inst.conn, subject_id)
    assert detail is not None


# ------------------------------------------------------------- reversal


def test_reversal_restores_the_active_identity(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    result = inst.reverse(subject_id)
    assert result.verified
    assert result.privacy_state == "ACTIVE"

    row = repository.get_person(inst.conn, subject_id)
    assert row["privacy_state"] == "ACTIVE"
    assert row["display_name"] == "Kwame Boateng"
    assert row["display_alias"] == result.display_alias  # alias is stable, not rotated

    email = (inst.source / "emails" / "01_extract-status.txt").read_text(encoding="utf-8")
    assert "Kwame Boateng" in email
    assert "k.boateng@relexsolutions.example" in email
    assert result.display_alias not in email


def test_reversal_preserves_evidence_and_relationships(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    before = {
        (r["evidence_id"], r["relation"])
        for r in inst.conn.execute(
            "SELECT evidence_id, relation FROM evidence_people WHERE subject_id = ?", (subject_id,)
        )
    }
    inst.pseudonymise(subject_id)
    inst.reverse(subject_id)
    after = {
        (r["evidence_id"], r["relation"])
        for r in inst.conn.execute(
            "SELECT evidence_id, relation FROM evidence_people WHERE subject_id = ?", (subject_id,)
        )
    }
    assert before <= after


def test_reversal_of_an_active_subject_fails(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    with pytest.raises(PrivacyOperationError):
        inst.reverse(subject_id)


def test_reversal_audit_record_omits_the_original_name(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    result = inst.reverse(subject_id)
    row = inst.conn.execute(
        "SELECT * FROM privacy_operations WHERE operation_id = ?", (result.operation_id,)
    ).fetchone()
    assert row is not None
    blob = json.dumps(dict(row)).lower()
    assert "kwame" not in blob and "boateng" not in blob


# ---------------------------------------------------- redaction/rewrite


def _target(name, *extra, emails=()):
    from app.privacy.targets import Target

    names = tuple(sorted({name, *extra}, key=len, reverse=True))
    return Target("p", name, "Participant TEST-01", names, tuple(emails))


def test_rewrite_handles_case_whitespace_possessive_subject_and_quoted_lines():
    from app.privacy.rewrite import rewrite_text

    t = _target("Kwame Boateng", emails=["k.boateng@relexsolutions.example"])
    text = (
        "Subject: Call with KWAME   BOATENG\n"
        "> kwame\nboateng wrote:\n"
        "Kwame Boateng's estimate; contact K.BOATENG@RELEXSOLUTIONS.EXAMPLE.\n"
    )
    out = rewrite_text(text, "emails", t)
    assert not re.search(r"kwame|boateng", out, re.IGNORECASE)
    # 3 name matches (subject line, quoted "kwame\nboateng", possessive) plus
    # 1 email match, which substitutes alias_email(alias), not the alias
    # string itself.
    assert out.count(t.display_alias) == 3
    from app.privacy.rewrite import alias_email

    assert out.count(alias_email(t.display_alias)) == 1


def test_rewrite_never_damages_a_different_person_with_an_overlapping_name():
    from app.privacy.rewrite import rewrite_text

    t = _target("Ann Lee")
    out = rewrite_text("Ann Lee met Joann Leeds and Ann Leeson.", "emails", t)
    assert out == f"{t.display_alias} met Joann Leeds and Ann Leeson."


def test_rewrite_handles_accented_names_and_uppercase_emails():
    from app.privacy.rewrite import rewrite_text

    t = _target("Nadia Öberg", emails=["n.oberg@x.example"])
    out = rewrite_text("NADIA ÖBERG wrote from N.OBERG@X.EXAMPLE", "reports", t)
    assert "berg" not in out.lower() and "x.example" not in out.lower()


def test_rewrite_uses_an_rfc2606_invalid_domain_never_a_real_looking_address():
    from app.privacy.rewrite import alias_email

    addr = alias_email("Participant Q7M4-N8")
    assert addr.endswith("@pseudonymised.invalid")
    assert addr == "participant-q7m4-n8@pseudonymised.invalid"


def test_no_locator_fingerprint_still_matches_the_original_text_of_a_rewritten_unit(inst):
    originals = [text for text in (r["raw_text"] for r in inst.units().values()) if "Kwame" in text]
    assert originals
    old_fingerprints = {repository.fingerprint(text) for text in originals}
    inst.pseudonymise()
    stored = {r[0] for r in inst.conn.execute("SELECT content_fingerprint FROM source_locators")}
    assert not (stored & old_fingerprints)


def test_a_normal_rebuild_keeps_the_case_dependency_record(inst):
    evidence_id = next(iter(inst.ids()))
    _add_case(inst.conn, "c1", "q", [evidence_id])
    ingest(inst.conn, inst.source, inst.provider)
    rows = inst.conn.execute("SELECT evidence_id FROM case_evidence WHERE case_id='c1'").fetchall()
    assert [r[0] for r in rows] == [evidence_id]


# ------------------------------------------------------------------ API


@pytest.fixture
def api(inst, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import deps
    from app.core import config
    from app.main import app

    monkeypatch.setenv("DATABASE_PATH", str(inst.db_path))
    monkeypatch.setenv("SOURCE_DATA_DIR", str(inst.source))
    monkeypatch.setenv("PSEUDONYM_VAULT_PATH", str(inst.vault_path))
    monkeypatch.setenv("PSEUDONYM_VAULT_KEY", inst.vault_key)
    monkeypatch.setenv("PRIVACY_ADMIN_TOKEN", "test-admin-token")
    config.get_settings.cache_clear()
    inst.conn.close()
    app.dependency_overrides[deps.get_embedding_provider] = lambda: inst.provider
    yield TestClient(app), inst
    app.dependency_overrides.clear()
    config.get_settings.cache_clear()
    deps.reset_shared_index()
    gate.reset_for_tests()
    inst.conn = connect(str(inst.db_path))


def _kwame_subject_id(client) -> str:
    people = client.get("/api/privacy/people").json()
    return next(p["subject_id"] for p in people if p["display_name"] == "Kwame Boateng")


def test_api_lists_people_and_previews_without_changing_anything(api):
    client, inst = api
    people = client.get("/api/privacy/people").json()
    kwame = next(p for p in people if p["display_name"] == "Kwame Boateng")
    assert kwame["privacy_state"] == "ACTIVE"
    assert kwame["display_alias"].startswith("Participant ")
    assert kwame["speaker_units"] >= 1
    preview = client.post("/api/privacy/preview", json={"subject_id": kwame["subject_id"]}).json()
    assert preview["files_to_rewrite"] == 5
    assert "Kwame Boateng" in inst.all_source_text()
    assert (
        client.post(
            "/api/privacy/preview", json={"subject_id": "00000000-0000-4000-8000-000000000000"}
        ).status_code
        == 404
    )


def test_api_pseudonymise_requires_admin_authentication(api):
    client, inst = api
    subject_id = _kwame_subject_id(client)
    no_auth = client.post("/api/privacy/pseudonymise", json={"subject_id": subject_id})
    assert no_auth.status_code == 401
    assert "Kwame Boateng" in inst.all_source_text()

    wrong_auth = client.post(
        "/api/privacy/pseudonymise",
        json={"subject_id": subject_id},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert wrong_auth.status_code == 401
    assert "Kwame Boateng" in inst.all_source_text()


def test_api_pseudonymise_succeeds_with_the_correct_admin_token(api):
    client, inst = api
    subject_id = _kwame_subject_id(client)
    response = client.post(
        "/api/privacy/pseudonymise",
        json={"subject_id": subject_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True and all(v == 0 for v in body["verification"].values())
    blob = json.dumps(body).lower()
    assert "kwame" not in blob and "boateng" not in blob
    from app.privacy import verify

    assert verify.scan_files(inst.source, NEEDLES) == 0
    assert response.headers.get("cache-control", "").startswith("private")


def test_api_serving_is_blocked_while_an_operation_is_locked(api):
    client, inst = api
    ops.acquire(inst.ops_dir, "op1")
    for method, path, kwargs in [
        ("get", "/api/privacy/people", {}),
        ("get", "/api/evidence/EV-x", {}),
        ("post", "/api/cases/query", {"json": {"query": "anything at all"}}),
    ]:
        assert getattr(client, method)(path, **kwargs).status_code == 503
    assert client.get("/api/health").status_code == 200
    ops.release(inst.ops_dir)
    assert client.get("/api/privacy/people").status_code == 200


def test_api_failed_pseudonymise_stays_locked_and_generic(api, monkeypatch):
    client, inst = api
    subject_id = _kwame_subject_id(client)
    monkeypatch.setattr(
        pseudonymise,
        "_rebuild_from_rewritten_source",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kwame detail")),
    )
    response = client.post(
        "/api/privacy/pseudonymise",
        json={"subject_id": subject_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 500
    assert "kwame" not in response.text.lower()
    assert client.get("/api/privacy/people").status_code == 503  # locked


def test_api_profile_and_history_are_db_hydrated_and_never_reveal_vault_state(api):
    client, inst = api
    subject_id = _kwame_subject_id(client)
    client.post(
        "/api/privacy/pseudonymise",
        json={"subject_id": subject_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    profile_response = client.get(f"/api/people/{subject_id}")
    assert profile_response.status_code == 200
    body = profile_response.json()
    assert body["privacy_state"] == "PSEUDONYMISED"
    assert body["display_name"] is None
    history_response = client.get(f"/api/people/{subject_id}/history")
    assert history_response.status_code == 200
    assert len(history_response.json()) >= 4
    assert client.get("/api/people/does-not-exist").status_code == 404


def test_api_admin_reversal_requires_authentication(api):
    client, inst = api
    subject_id = _kwame_subject_id(client)
    client.post(
        "/api/privacy/pseudonymise",
        json={"subject_id": subject_id},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    unauth = client.post(
        f"/api/admin/people/{subject_id}/reverse-pseudonymisation", json={"confirm": True}
    )
    assert unauth.status_code == 401

    unconfirmed = client.post(
        f"/api/admin/people/{subject_id}/reverse-pseudonymisation",
        json={"confirm": False},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert unconfirmed.status_code == 400
    assert "Kwame Boateng" not in inst.all_source_text()  # still pseudonymised

    authed = client.post(
        f"/api/admin/people/{subject_id}/reverse-pseudonymisation",
        json={"confirm": True},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert authed.status_code == 200
    body = authed.json()
    assert body["privacy_state"] == "ACTIVE"
    assert "kwame" not in json.dumps(body).lower()
    assert "Kwame Boateng" in inst.all_source_text()
