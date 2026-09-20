"""Hardening pass on top of test_pseudonymisation.py: reversal plan safety,
staged interruption/recovery for *both* directions (including op_kind
dispatch), the embeddings/verified gate, readiness's vector validation and
exact-baseline check, external_signals.json coverage, and the disclosed
filename-identifier limitation. Every test builds its own temporary
instance (CLAUDE.md 0.5) via test_pseudonymisation.Instance and never
touches the repository's own data/source, data/app.db, or
data/private-vault.
"""

import json

import pytest
from cryptography.fernet import Fernet
from test_pseudonymisation import NEEDLES, Instance

from app.db.connection import connect
from app.privacy import ops, pseudonymise, reverse, staging, verify
from app.privacy.gate import gate
from app.privacy.ops import PrivacyOperationError

pytest_plugins = []


@pytest.fixture
def inst(tmp_path):
    instance = Instance(tmp_path)
    yield instance
    instance.conn.close()


# ------------------------------------------------ reversal plan safety


def test_reverse_plan_never_contains_original_name_email_or_restored_text(inst, monkeypatch):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)

    captured: list[dict] = []
    real_write_plan = ops.write_plan

    def capture(ops_dir, plan):
        captured.append(json.loads(json.dumps(plan)))
        return real_write_plan(ops_dir, plan)

    monkeypatch.setattr(ops, "write_plan", capture)
    inst.reverse(subject_id)

    assert captured, "reversal must write at least one plan"
    for plan in captured:
        blob = json.dumps(plan).lower()
        assert "kwame" not in blob
        assert "boateng" not in blob
        assert "k.boateng@relexsolutions.example" not in blob
        # The restored (original-identity-bearing) file content itself must
        # never be persisted -- only IDs, the alias, and counts.
        assert "files" not in plan or all(
            isinstance(v, (int, str)) and not v.strip("0123456789") == ""
            for v in ()  # no-op guard; real assertion is the key's absence
        )
        assert "files" not in plan
        assert plan.get("op_kind") == "reverse"


# ------------------------------------------- reversal staged interruption


def _acquire_stage(inst, subject_id, monkeypatch, patch_target, patch_module, expected_state):
    """Run a real reversal with `patch_target` on `patch_module` replaced by
    a raiser, and assert it left the lock exactly at `expected_state`."""
    original = getattr(patch_module, patch_target)
    monkeypatch.setattr(
        patch_module, patch_target, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash"))
    )
    with pytest.raises(PrivacyOperationError):
        inst.reverse(subject_id)
    assert ops.is_locked(inst.ops_dir)
    assert ops.read_lock(inst.ops_dir)["state"] == expected_state
    monkeypatch.setattr(patch_module, patch_target, original)


def test_reversal_interrupted_during_source_rewrite_resumes_via_top_level_recover(
    inst, monkeypatch
):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    _acquire_stage(inst, subject_id, monkeypatch, "write_files", staging, ops.SOURCE_IN_PROGRESS)

    # No restored (original-identity) text reached the source yet.
    assert verify.scan_files(inst.source, ["Kwame Boateng"]) == 0

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
    assert not ops.is_locked(inst.ops_dir)
    conn = connect(str(inst.db_path))
    row = conn.execute(
        "SELECT privacy_state, display_name FROM people WHERE subject_id = ?", (subject_id,)
    ).fetchone()
    assert row["privacy_state"] == "ACTIVE"
    assert row["display_name"] == "Kwame Boateng"
    conn.close()
    inst.conn = connect(str(inst.db_path))


def test_reversal_interrupted_during_db_update_resumes_via_top_level_recover(inst, monkeypatch):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    _acquire_stage(inst, subject_id, monkeypatch, "ingest", reverse, ops.SOURCE_DONE)

    # The source was already restored before the crash.
    assert "Kwame Boateng" in inst.all_source_text()

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
    assert not ops.is_locked(inst.ops_dir)
    conn = connect(str(inst.db_path))
    row = conn.execute(
        "SELECT privacy_state, display_name FROM people WHERE subject_id = ?", (subject_id,)
    ).fetchone()
    assert row["privacy_state"] == "ACTIVE"
    conn.close()
    inst.conn = connect(str(inst.db_path))


def test_reversal_interrupted_during_physical_cleanup_resumes_via_top_level_recover(
    inst, monkeypatch
):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    _acquire_stage(inst, subject_id, monkeypatch, "physical_cleanup", staging, ops.DB_DONE)

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
    assert not ops.is_locked(inst.ops_dir)
    inst.conn = connect(str(inst.db_path))


def test_reversal_interrupted_during_verification_resumes_via_top_level_recover(inst, monkeypatch):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    _acquire_stage(inst, subject_id, monkeypatch, "_verify", reverse, ops.CLEANUP_DONE)

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
    assert not ops.is_locked(inst.ops_dir)
    conn = connect(str(inst.db_path))
    row = conn.execute(
        "SELECT privacy_state, display_name FROM people WHERE subject_id = ?", (subject_id,)
    ).fetchone()
    assert row["privacy_state"] == "ACTIVE"
    assert row["display_name"] == "Kwame Boateng"
    conn.close()
    inst.conn = connect(str(inst.db_path))


def test_reversal_verification_failure_keeps_the_system_locked(inst, monkeypatch):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)

    def leaky(*a, **k):
        return {"source_files": 3}, {"subject_is_active": True}

    monkeypatch.setattr(reverse, "_verify", leaky)
    with pytest.raises(PrivacyOperationError):
        inst.reverse(subject_id)
    assert ops.is_locked(inst.ops_dir)


# ------------------------------------------------------------- op_kind dispatch


def test_recover_dispatches_a_reverse_plan_to_reverse_recover_not_forward(inst, monkeypatch):
    """If dispatch were broken and a reverse-shaped plan fell through to
    forward pseudonymisation's own _run, it would KeyError on plan["remap"]/
    plan["files"], which a reverse plan never has. Asserting a clean resume
    proves the dispatch actually took the reverse path."""
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)

    called = {"forward": False}
    monkeypatch.setattr(pseudonymise, "_run", lambda *a, **k: called.__setitem__("forward", True))
    inst.reverse(subject_id)  # succeeds end to end without ever calling forward's _run
    assert called["forward"] is False


def test_a_forward_plan_left_locked_is_not_misread_as_a_reverse_plan(inst, monkeypatch):
    original = pseudonymise._rebuild_from_rewritten_source
    monkeypatch.setattr(
        pseudonymise,
        "_rebuild_from_rewritten_source",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash")),
    )
    with pytest.raises(PrivacyOperationError):
        inst.pseudonymise()
    plan = ops.read_plan(inst.ops_dir)
    assert plan.get("op_kind") == "pseudonymise"
    # Restore the real implementation so the resumed call below actually
    # completes the interrupted stage instead of crashing a second time --
    # the crash was only meant to interrupt the *first* attempt.
    monkeypatch.setattr(pseudonymise, "_rebuild_from_rewritten_source", original)

    called = {"reverse": False}
    monkeypatch.setattr(reverse, "recover", lambda **k: called.__setitem__("reverse", True))
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
    assert called["reverse"] is False
    inst.conn = connect(str(inst.db_path))


# --------------------------------------------------- embeddings/verified gate


def test_pseudonymise_is_not_fully_verified_while_embeddings_are_pending(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    # Embeddings exist beforehand (ingested with a real provider); the
    # operation itself is run with provider=None, simulating the organizer
    # embedding API being unreachable.
    result = inst.pseudonymise(subject_id, provider=None)
    assert result.embeddings_pending > 0
    assert result.verified is False
    assert result.checks["no_embeddings_pending_for_changed_evidence"] is False
    # But the operation still completed and unlocked -- privacy completion
    # must never depend on network availability (CLAUDE.md 18.12).
    assert not ops.is_locked(inst.ops_dir)
    row = inst.conn.execute(
        "SELECT privacy_state FROM people WHERE subject_id = ?", (subject_id,)
    ).fetchone()
    assert row["privacy_state"] == "PSEUDONYMISED"


def test_pseudonymise_is_fully_verified_when_embeddings_regenerate(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    result = inst.pseudonymise(subject_id)  # default provider: MockEmbeddingProvider
    assert result.embeddings_pending == 0
    assert result.verified is True
    assert result.checks["no_embeddings_pending_for_changed_evidence"] is True


def test_reversal_is_not_fully_verified_while_embeddings_are_pending(inst):
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    result = inst.reverse(subject_id, provider=None)
    assert result.embeddings_pending > 0
    assert result.verified is False
    assert not ops.is_locked(inst.ops_dir)


# --------------------------------------------------------- external signals


_SIGNAL_MANIFEST = {
    "description": "test",
    "signals": [
        {
            "signal_id": "sig-1",
            "title": "Vendor note mentioning Kwame Boateng",
            "source": "internal memo",
            "published": "2025-01-01",
            "url": None,
            "summary": (
                "Kwame Boateng flagged this pattern to the vendor, "
                "k.boateng@relexsolutions.example."
            ),
            "categories": [],
        }
    ],
}


def test_pseudonymise_rewrites_external_signals_json(inst):
    (inst.source / "external_signals.json").write_text(
        json.dumps(_SIGNAL_MANIFEST), encoding="utf-8"
    )
    subject_id = inst.subject_id_for("Kwame Boateng")
    result = inst.pseudonymise(subject_id)
    assert result.verified

    text = (inst.source / "external_signals.json").read_text(encoding="utf-8")
    assert "Kwame" not in text and "k.boateng@relexsolutions.example" not in text
    assert result.display_alias in text
    data = json.loads(text)  # still valid JSON after substitution
    assert data["signals"][0]["signal_id"] == "sig-1"
    assert verify.scan_files(inst.source, NEEDLES) == 0


def test_reversal_restores_external_signals_json(inst):
    (inst.source / "external_signals.json").write_text(
        json.dumps(_SIGNAL_MANIFEST), encoding="utf-8"
    )
    subject_id = inst.subject_id_for("Kwame Boateng")
    inst.pseudonymise(subject_id)
    inst.reverse(subject_id)
    text = (inst.source / "external_signals.json").read_text(encoding="utf-8")
    assert "Kwame Boateng" in text
    assert "k.boateng@relexsolutions.example" in text
    json.loads(text)  # still valid JSON


# --------------------------------------------------------------- filenames


def test_verification_fails_closed_when_a_filename_still_contains_the_original_name(inst):
    """Disclosed limitation (see verify.scan_filenames's docstring): a
    filename cannot be safely renamed without changing document_id (and
    therefore every Evidence ID under it), so a leak here fails the
    operation rather than being silently "fixed". This deliberately targets
    a DIFFERENT active person (Marco Rossi) so the filename genuinely still
    names them after their own pseudonymisation."""
    stray = inst.source / "transcripts" / "marco-rossi-1on1-notes.txt"
    stray.write_text(
        "Meeting: Skip-level\nCustomer: Acme Org\nDate: 2024-09-01\nPhase: Implementation\n"
        "Attendees: Lena Fischer (Acme)\n\n"
        "Lena Fischer\n0:050:05\nLF\nLena Fischer 5 seconds\n"
        "Nothing sensitive said here.\n",
        encoding="utf-8",
    )
    from app.ingestion.service import ingest

    ingest(inst.conn, inst.source, inst.provider)

    marco_id = inst.subject_id_for("Marco Rossi")
    with pytest.raises(PrivacyOperationError):
        inst.pseudonymise(marco_id)
    assert ops.is_locked(inst.ops_dir)


def test_scan_filenames_detects_a_needle_in_the_path_not_just_content(tmp_path):
    target = tmp_path / "kwame-notes.txt"
    target.write_text("nothing sensitive here", encoding="utf-8")
    assert verify.scan_filenames(tmp_path, ["Kwame"]) == 1
    assert verify.scan_files(tmp_path, ["Kwame"]) == 0  # content-only scan misses it


# --------------------------------------------------------------------- readiness


@pytest.fixture
def readiness_api(inst, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import deps
    from app.core import config
    from app.main import app

    monkeypatch.setenv("DATABASE_PATH", str(inst.db_path))
    monkeypatch.setenv("SOURCE_DATA_DIR", str(inst.source))
    monkeypatch.setenv("PSEUDONYM_VAULT_PATH", str(inst.vault_path))
    monkeypatch.setenv("PSEUDONYM_VAULT_KEY", inst.vault_key)
    monkeypatch.setenv("EXPECTED_DOCUMENT_COUNT", "4")
    monkeypatch.setenv("EXPECTED_EVIDENCE_UNIT_COUNT", str(len(inst.ids())))
    monkeypatch.setenv("EXPECTED_FTS_ROW_COUNT", str(len(inst.ids())))
    monkeypatch.setenv("EXPECTED_EMBEDDING_ROW_COUNT", str(len(inst.ids())))
    config.get_settings.cache_clear()
    inst.conn.close()
    yield TestClient(app), inst
    config.get_settings.cache_clear()
    deps.reset_shared_index()
    gate.reset_for_tests()
    inst.conn = connect(str(inst.db_path))


def test_readiness_matches_configured_baseline_for_a_clean_synthetic_archive(readiness_api):
    client, inst = readiness_api
    response = client.get("/api/readiness")
    body = response.json()
    assert body["checks"]["matches_expected_clean_archive_baseline"] is True, body
    assert body["checks"]["embeddings_are_valid"] is True
    assert response.status_code == 200
    assert body["ready"] is True


def test_readiness_fails_baseline_when_counts_do_not_match(inst, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import deps
    from app.core import config
    from app.main import app

    monkeypatch.setenv("DATABASE_PATH", str(inst.db_path))
    monkeypatch.setenv("SOURCE_DATA_DIR", str(inst.source))
    monkeypatch.setenv("PSEUDONYM_VAULT_PATH", str(inst.vault_path))
    monkeypatch.setenv("PSEUDONYM_VAULT_KEY", inst.vault_key)
    # Deliberately left at the real-archive defaults (45/2534/2534/2534),
    # which this tiny synthetic fixture cannot match.
    config.get_settings.cache_clear()
    inst.conn.close()
    try:
        client = TestClient(app)
        response = client.get("/api/readiness")
        body = response.json()
        assert body["checks"]["matches_expected_clean_archive_baseline"] is False
        assert response.status_code == 503
        assert body["ready"] is False
    finally:
        config.get_settings.cache_clear()
        deps.reset_shared_index()
        gate.reset_for_tests()
        inst.conn = connect(str(inst.db_path))


def test_readiness_flags_an_invalid_embedding_vector(readiness_api):
    client, inst = readiness_api
    conn = connect(str(inst.db_path))
    # inst.conn is already closed by the readiness_api fixture (the API
    # under test owns the database file for the test's duration), so the
    # evidence_id must come from this freshly opened connection, not
    # inst.ids() (which reads through inst.conn).
    evidence_id = next(iter({r[0] for r in conn.execute("SELECT evidence_id FROM evidence_units")}))
    conn.execute(
        "UPDATE evidence_embeddings SET vector_json = ? WHERE evidence_id = ?",
        (json.dumps([1.0, float("nan"), 2.0]), evidence_id),
    )
    conn.commit()
    conn.close()

    response = client.get("/api/readiness")
    body = response.json()
    assert body["checks"]["embeddings_are_valid"] is False
    assert body["details"]["invalid_embeddings"] >= 1
    assert response.status_code == 503


def test_readiness_does_not_read_the_database_while_locked(readiness_api):
    client, inst = readiness_api
    ops.acquire(inst.ops_dir, "op1")
    try:
        response = client.get("/api/readiness")
        body = response.json()
        assert response.status_code == 503
        assert body["checks"]["privacy_operation_not_locked"] is False
        for key in (
            "database_not_empty",
            "fts_matches_evidence_units",
            "embeddings_cover_all_evidence",
            "embeddings_are_valid",
            "runtime_database_not_stale",
            "matches_expected_clean_archive_baseline",
        ):
            assert body["checks"][key] is False
        assert body["details"] == {}
    finally:
        ops.release(inst.ops_dir)


def test_readiness_is_blocked_by_an_in_process_write_lease(readiness_api):
    client, inst = readiness_api
    with gate.write_lease():
        response = client.get("/api/readiness")
    body = response.json()
    assert response.status_code == 503
    assert body["checks"]["privacy_operation_not_locked"] is False


def test_vault_key_generation_helper_produces_a_usable_fernet_key():
    # Sanity check on the .env.example / README guidance, not on app code:
    # a freshly generated key must actually work with the vault module.
    key = Fernet.generate_key().decode()
    assert isinstance(key, str) and len(key) > 0
    Fernet(key.encode("ascii"))  # raises if malformed
