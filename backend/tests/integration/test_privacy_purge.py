"""Deletion / anonymization end to end, on a synthetic corpus.

Every test builds its own temporary source directory, database, artifacts
and cache folders (CLAUDE.md 0.5) and never touches the repository's own
data/source or data/app.db.
"""

import json
import re
import sqlite3
from pathlib import Path

import pytest

from app.core import anonymous_labels as labels
from app.db.connection import connect
from app.ingestion.embeddings import MockEmbeddingProvider
from app.ingestion.service import ingest
from app.privacy import ops, service, verify
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
        # Derived artifacts/cache that contain the name must be purged too.
        (self.artifacts / "export.json").write_text('{"who": "Kwame Boateng"}', encoding="utf-8")
        (self.cache / "tmp.txt").write_text("k.boateng@relexsolutions.example", encoding="utf-8")

    def purge(self, provider="default", **kwargs):
        return service.purge(
            self.conn,
            source_dir=self.source,
            db_path=self.db_path,
            ops_dir=self.ops_dir,
            person_id="kwame-boateng",
            artifact_dirs=[self.artifacts, self.cache],
            provider=self.provider if provider == "default" else provider,
            **kwargs,
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


def test_setup_sees_the_person_and_the_reviewed_short_alias(inst):
    aliases = {
        r[0]
        for r in inst.conn.execute(
            "SELECT alias FROM person_aliases WHERE person_id = 'kwame-boateng'"
        )
    }
    assert {"Kwame Boateng", "Kwame", "k.boateng@relexsolutions.example"} <= aliases


def test_preview_reports_counts_without_changing_anything(inst):
    before = inst.all_source_text()
    result = service.preview(inst.conn, inst.source, "kwame-boateng")
    assert result.speaker_units >= 1 and result.units_to_anonymize >= 4
    assert result.files_to_sanitize == 5  # 4 evidence files + the reviewed manifest
    assert inst.all_source_text() == before
    assert service.preview(inst.conn, inst.source, "nobody") is None


def test_purge_removes_every_tracked_identifier_from_every_surface(inst):
    result = inst.purge()
    assert result.verified and all(v == 0 for v in result.verification.values())

    # Independent of the service's own verifier.
    assert verify.scan_files(inst.source, NEEDLES) == 0
    assert verify.scan_files(inst.artifacts, NEEDLES) == 0
    assert verify.scan_files(inst.cache, NEEDLES) == 0
    conn = sqlite3.connect(inst.db_path)
    conn.row_factory = sqlite3.Row
    assert verify.scan_database_rows(conn, NEEDLES) == 0
    conn.close()
    assert verify.scan_database_files(inst.db_path, NEEDLES) == 0
    assert (
        inst.conn.execute("SELECT COUNT(*) FROM people WHERE person_id='kwame-boateng'").fetchone()[
            0
        ]
        == 0
    )


def test_structural_metadata_is_sanitized_not_just_body_text(inst):
    inst.purge()
    teams = (inst.source / "transcripts" / "01_weekly-sync.txt").read_text(encoding="utf-8")
    assert "Attendees: Marco Rossi (RELEX), Lena Fischer (Acme)" in teams
    assert "\nKB\n" not in teams  # initials chrome
    assert f"{labels.REDACTED_SPEAKER} 10 seconds" in teams
    email = (inst.source / "emails" / "01_extract-status.txt").read_text(encoding="utf-8")
    assert f"From: {labels.REDACTED_SENDER}" in email
    assert "+44 7700 900 318" not in email  # signature block removed with the name
    assert "Technical Consultant" not in email
    assert "lena.fischer@acme-org.example" in email  # other people are untouched


def test_organizational_evidence_survives_anonymized_and_retrievable(inst):
    inst.purge()
    texts = " || ".join(r["raw_text"] for r in inst.units().values())
    assert "shelf life is populated on forty-eight percent" in texts
    assert "the extract succeeded" in texts.lower() or "extract succeeded" in texts
    speakers = {r["speaker_sender"] for r in inst.units().values()}
    assert labels.REDACTED_SPEAKER in speakers
    hit = inst.conn.execute(
        "SELECT evidence_id FROM evidence_fts WHERE evidence_fts MATCH 'forty'"
    ).fetchall()
    assert hit


def test_every_evidence_id_is_stable_across_the_operation(inst):
    before = inst.ids()
    inst.purge()
    assert inst.ids() == before


def test_a_rebuild_after_the_operation_does_not_resurrect_anything(inst):
    inst.purge()
    ids = inst.ids()
    ingest(inst.conn, inst.source, inst.provider)  # the normal rebuild command
    assert inst.ids() == ids
    assert (
        inst.conn.execute("SELECT COUNT(*) FROM people WHERE person_id='kwame-boateng'").fetchone()[
            0
        ]
        == 0
    )
    assert verify.scan_database_rows(inst.conn, NEEDLES) == 0
    assert verify.scan_files(inst.source, NEEDLES) == 0


def test_markers_never_become_people_aliases_or_relations(inst):
    inst.purge()
    names = {r[0] for r in inst.conn.execute("SELECT canonical_name FROM people")}
    aliases = {r[0] for r in inst.conn.execute("SELECT alias FROM person_aliases")}
    for marker in labels.REDACTION_MARKERS:
        assert marker not in names and marker not in aliases


def test_reviewed_identity_manifest_entry_is_removed(inst):
    inst.purge()
    data = json.loads((inst.source / "reviewed_identities.json").read_text(encoding="utf-8"))
    assert data["entries"] == []


def test_unchanged_embeddings_are_kept_and_changed_ones_regenerated_from_sanitized_text(inst):
    old = {
        r[0]: r[1]
        for r in inst.conn.execute("SELECT evidence_id, vector_json FROM evidence_embeddings")
    }
    units_before = {i: r["raw_text"] for i, r in inst.units().items()}
    result = inst.purge()
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
            assert new[evidence_id] == expected  # of the sanitized text, not the old
            assert new[evidence_id] != old[evidence_id]
        else:
            assert new[evidence_id] == old[evidence_id]


def test_without_a_provider_no_stale_embedding_survives_and_degradation_is_reported(inst):
    changed_before = {
        i for i, r in inst.units().items() if re.search(r"kwame", r["raw_text"], re.IGNORECASE)
    }
    result = inst.purge(provider=None)
    assert result.embeddings_regenerated == 0
    assert result.embeddings_pending >= len(changed_before) > 0
    present = {r[0] for r in inst.conn.execute("SELECT evidence_id FROM evidence_embeddings")}
    assert not (present & changed_before)  # old vectors of changed text are gone


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
    result = inst.purge()
    remaining = {r[0] for r in inst.conn.execute("SELECT case_id FROM cases")}
    assert remaining == {"c-clean"} and result.cases_invalidated == 2
    assert (
        inst.conn.execute(
            "SELECT COUNT(*) FROM case_evidence WHERE case_id IN ('c-cites','c-prose')"
        ).fetchone()[0]
        == 0
    )


def test_the_lock_is_released_and_the_ops_folder_left_empty(inst):
    inst.purge()
    assert not ops.is_locked(inst.ops_dir)
    assert list(inst.ops_dir.iterdir()) == []


def test_an_unreviewed_first_name_is_not_redacted_because_it_may_be_someone_else(tmp_path):
    root = tmp_path
    instance = Instance(root)
    manifest = {"description": "x", "entries": []}  # no reviewed 'Kwame' alias
    (instance.source / "reviewed_identities.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    ingest(instance.conn, instance.source, instance.provider)
    instance.purge()
    email = (instance.source / "emails" / "01_extract-status.txt").read_text(encoding="utf-8")
    # The full name is gone; the bare, unreviewed first name is left alone.
    assert "Kwame Boateng" not in email and "Kwame is checking" in email
    instance.conn.close()


def test_purge_of_an_unknown_person_fails_before_locking(inst):
    with pytest.raises(PrivacyOperationError):
        service.purge(
            inst.conn,
            source_dir=inst.source,
            db_path=inst.db_path,
            ops_dir=inst.ops_dir,
            person_id="nobody",
        )
    assert not ops.is_locked(inst.ops_dir)


# ------------------------------------------------- locking and recovery


def test_a_failed_operation_stays_locked_and_never_reports_success(inst, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("k.boateng@relexsolutions.example detail that must not leak")

    monkeypatch.setattr(service, "_rebuild_from_sanitized_source", boom)
    with pytest.raises(PrivacyOperationError) as info:
        inst.purge()
    assert "boateng" not in str(info.value).lower()
    assert ops.is_locked(inst.ops_dir)
    with pytest.raises(PrivacyLockedError):
        ops.assert_unlocked(inst.ops_dir)
    with pytest.raises(PrivacyLockedError):
        inst.purge()  # a second operation cannot start


def test_interrupted_operation_resumes_to_completion(inst, monkeypatch):
    original = service._rebuild_from_sanitized_source
    monkeypatch.setattr(
        service,
        "_rebuild_from_sanitized_source",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash")),
    )
    with pytest.raises(PrivacyOperationError):
        inst.purge()
    assert ops.read_lock(inst.ops_dir)["state"] == ops.SOURCE_DONE
    # Source was already sanitized before the crash.
    assert verify.scan_files(inst.source, NEEDLES) == 0

    monkeypatch.setattr(service, "_rebuild_from_sanitized_source", original)
    inst.conn.close()
    outcome = service.recover(
        source_dir=inst.source,
        db_path=inst.db_path,
        ops_dir=inst.ops_dir,
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
    assert service.recover(source_dir=tmp_path, db_path=tmp_path / "x.db", ops_dir=ops_dir) == (
        "cleared orphan lock"
    )
    assert not ops.is_locked(ops_dir)


def test_finalizing_with_the_plan_already_removed_is_finished_not_treated_as_corruption(tmp_path):
    ops_dir = tmp_path / "ops"
    ops.acquire(ops_dir, "op1")
    ops.set_state(ops_dir, ops.FINALIZING)
    assert service.recover(source_dir=tmp_path, db_path=tmp_path / "x.db", ops_dir=ops_dir) == (
        "finalized"
    )
    assert not ops.is_locked(ops_dir)


@pytest.mark.parametrize("state", [ops.SOURCE_IN_PROGRESS, ops.DB_DONE, "CORRUPT", "WHAT"])
def test_any_other_shape_without_a_readable_plan_fails_closed(tmp_path, state):
    ops_dir = tmp_path / "ops"
    ops.acquire(ops_dir, "op1")
    ops.set_state(ops_dir, state)
    with pytest.raises(PrivacyOperationError):
        service.recover(source_dir=tmp_path, db_path=tmp_path / "x.db", ops_dir=ops_dir)
    assert ops.is_locked(ops_dir)


def test_a_torn_plan_file_fails_closed(tmp_path):
    ops_dir = tmp_path / "ops"
    ops.acquire(ops_dir, "op1")
    ops.set_state(ops_dir, ops.SOURCE_DONE)
    (ops_dir / ops.PLAN_NAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(PrivacyOperationError):
        service.recover(source_dir=tmp_path, db_path=tmp_path / "x.db", ops_dir=ops_dir)
    assert ops.is_locked(ops_dir)


def test_atomic_write_never_leaves_a_torn_file(tmp_path):
    target = tmp_path / "f.txt"
    ops.atomic_write(target, "one")
    ops.atomic_write(target, "two")
    assert target.read_text() == "two"
    assert [p.name for p in tmp_path.iterdir()] == ["f.txt"]


def test_verification_failure_keeps_the_system_locked(inst, monkeypatch):
    real = verify.verify

    def leaky(**kwargs):
        report = real(**kwargs)
        report.counts["source_files"] = 3
        return report

    monkeypatch.setattr(verify, "verify", leaky)
    with pytest.raises(PrivacyOperationError):
        inst.purge()
    assert ops.is_locked(inst.ops_dir)


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
    config.get_settings.cache_clear()
    inst.conn.close()
    app.dependency_overrides[deps.get_embedding_provider] = lambda: inst.provider
    yield TestClient(app), inst
    app.dependency_overrides.clear()
    config.get_settings.cache_clear()
    deps.reset_shared_index()
    inst.conn = connect(str(inst.db_path))


def test_api_lists_people_and_previews_without_changing_anything(api):
    client, inst = api
    people = client.get("/api/privacy/people").json()
    kwame = next(p for p in people if p["person_id"] == "kwame-boateng")
    assert kwame["speaker_units"] >= 1
    preview = client.post("/api/privacy/preview", json={"person_id": "kwame-boateng"}).json()
    assert preview["files_to_sanitize"] == 5
    assert "Kwame Boateng" in inst.all_source_text()
    assert client.post("/api/privacy/preview", json={"person_id": "nobody"}).status_code == 404


def test_api_purge_requires_explicit_confirmation(api):
    client, inst = api
    assert client.post("/api/privacy/purge", json={"person_id": "kwame-boateng"}).status_code == 400
    assert "Kwame Boateng" in inst.all_source_text()


def test_api_purge_returns_counts_and_verification_never_content(api):
    client, inst = api
    response = client.post(
        "/api/privacy/purge", json={"person_id": "kwame-boateng", "confirm": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True and all(v == 0 for v in body["verification"].values())
    blob = json.dumps(body).lower()
    assert "kwame" not in blob and "boateng" not in blob
    assert verify.scan_files(inst.source, NEEDLES) == 0


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


def test_api_failed_purge_stays_locked_and_generic(api, monkeypatch):
    client, inst = api
    monkeypatch.setattr(
        service,
        "_rebuild_from_sanitized_source",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kwame detail")),
    )
    response = client.post(
        "/api/privacy/purge", json={"person_id": "kwame-boateng", "confirm": True}
    )
    assert response.status_code == 500
    assert "kwame" not in response.text.lower()
    assert client.get("/api/privacy/people").status_code == 503  # locked


def test_ingest_cli_refuses_while_locked(inst):
    import subprocess
    import sys

    ops.acquire(inst.ops_dir, "op1")
    script = Path(__file__).resolve().parents[3] / "scripts" / "ingest.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--skip-embeddings",
            "--source",
            str(inst.source),
            "--db-path",
            str(inst.db_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "privacy operation" in (result.stderr + result.stdout)


def test_two_people_can_be_removed_one_after_the_other(inst):
    ids = inst.ids()
    inst.purge()
    second = service.purge(
        inst.conn,
        source_dir=inst.source,
        db_path=inst.db_path,
        ops_dir=inst.ops_dir,
        person_id="marco-rossi",
        artifact_dirs=[inst.artifacts, inst.cache],
        provider=inst.provider,
    )
    assert second.verified
    assert inst.ids() == ids
    assert verify.scan_files(inst.source, NEEDLES + ["marco rossi", "marco.rossi@"]) == 0
    assert (
        inst.conn.execute("SELECT COUNT(*) FROM people WHERE person_id='marco-rossi'").fetchone()[0]
        == 0
    )
    # The first person stays gone and the other survivors are untouched.
    assert (
        inst.conn.execute("SELECT COUNT(*) FROM people WHERE person_id='lena-fischer'").fetchone()[
            0
        ]
        == 1
    )


def test_group_boundaries_are_backfilled_for_a_database_that_predates_them(inst):
    ids = inst.ids()
    inst.conn.execute("UPDATE source_locators SET starts_group = NULL")
    inst.conn.commit()
    inst.purge()
    service.purge(
        inst.conn,
        source_dir=inst.source,
        db_path=inst.db_path,
        ops_dir=inst.ops_dir,
        person_id="marco-rossi",
        artifact_dirs=[inst.artifacts, inst.cache],
        provider=inst.provider,
    )
    # Two different removed speakers are adjacent in the weekly-sync transcript;
    # their turns must not fuse and no Evidence ID may disappear.
    assert inst.ids() == ids
    speakers = [
        r["speaker_sender"]
        for r in inst.conn.execute(
            "SELECT speaker_sender FROM evidence_units WHERE document_id = '01_weekly-sync' "
            "ORDER BY unit_index"
        )
    ]
    assert speakers.count(labels.REDACTED_SPEAKER) == 2


# ------------------------------------------- redaction edge cases (unit-level)


def _target(name, *extra, emails=()):
    from app.privacy.targets import Target

    return Target("p", name, tuple(sorted({name, *extra}, key=len, reverse=True)), tuple(emails))


def test_redaction_handles_case_whitespace_possessive_subject_and_quoted_lines():
    from app.privacy.redact import sanitize_text

    t = _target("Kwame Boateng", emails=["k.boateng@relexsolutions.example"])
    text = (
        "Subject: Call with KWAME   BOATENG\n"
        "> kwame\nboateng wrote:\n"
        "Kwame Boateng's estimate; contact K.BOATENG@RELEXSOLUTIONS.EXAMPLE.\n"
    )
    out = sanitize_text(text, "emails", t)
    assert not re.search(r"kwame|boateng", out, re.IGNORECASE)
    assert out.count(labels.REDACTED_PERSON) == 4


def test_redaction_never_damages_a_different_person_with_an_overlapping_name():
    from app.privacy.redact import sanitize_text

    t = _target("Ann Lee")
    out = sanitize_text("Ann Lee met Joann Leeds and Ann Leeson.", "emails", t)
    assert out == f"{labels.REDACTED_PERSON} met Joann Leeds and Ann Leeson."


def test_redaction_handles_accented_names_and_uppercase_emails():
    from app.privacy.redact import sanitize_text

    t = _target("Nadia Öberg", emails=["n.oberg@x.example"])
    out = sanitize_text("NADIA ÖBERG wrote from N.OBERG@X.EXAMPLE", "reports", t)
    assert "berg" not in out.lower() and "x.example" not in out.lower()


def test_no_locator_fingerprint_still_matches_the_original_text_of_a_redacted_unit(inst):
    from app.db import repository

    originals = [text for text in (r["raw_text"] for r in inst.units().values()) if "Kwame" in text]
    assert originals
    old_fingerprints = {repository.fingerprint(text) for text in originals}
    inst.purge()
    stored = {r[0] for r in inst.conn.execute("SELECT content_fingerprint FROM source_locators")}
    assert not (stored & old_fingerprints)


def test_no_staging_table_survives_a_completed_operation(inst):
    inst.purge()
    tables = {r[0] for r in inst.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "privacy_embedding_stash" not in tables


def test_plan_and_lock_are_private_to_the_owner(inst, monkeypatch):
    seen = {}
    real = service._rebuild_from_sanitized_source

    def peek(*args, **kwargs):
        seen["dir"] = inst.ops_dir.stat().st_mode & 0o777
        seen["plan"] = (inst.ops_dir / ops.PLAN_NAME).stat().st_mode & 0o777
        return real(*args, **kwargs)

    monkeypatch.setattr(service, "_rebuild_from_sanitized_source", peek)
    inst.purge()
    assert seen["dir"] == 0o700 and seen["plan"] == 0o600


def test_reviewed_spoken_employee_number_is_redacted_with_the_person(inst):
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

    result = inst.purge()

    assert result.verified
    text = kickoff.read_text(encoding="utf-8")
    assert "five one oh three" not in text and "Kwame" not in text
    assert "if your system wants that" in text  # the non-personal remainder survives
    assert verify.scan_files(inst.source, [*NEEDLES, "five one oh three"]) == 0
    assert verify.scan_database_files(inst.db_path, [*NEEDLES, "five one oh three"]) == 0
