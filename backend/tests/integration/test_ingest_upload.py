"""The Add Evidence upload API.

Every path -- source directory, database, privacy-operations directory and
staging cache -- lives under pytest's tmp_path (CLAUDE.md 0.5), so uploads,
failures and rebuilds here can never touch the repository's own data/.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api import ingestion as ingestion_api
from app.db.connection import connect
from app.ingestion import service, upload
from app.ingestion.embeddings import MockEmbeddingProvider
from app.main import app
from app.privacy import ops
from app.retrieval import lexical

SEED_EMAIL = """Subject: Seed thread
From: Ana Duarte <ana.duarte@relexsolutions.example>
Date: Monday, January 6, 2025 09:00 AM
To: Lena Fischer <lena.fischer@acme-org.example>

The seed pallet count was confirmed.
"""

EMAIL = """Subject: Zephyr label pilot
From: Marco Rossi <marco.rossi@relexsolutions.example>
Date: Tuesday, March 4, 2025 10:30 AM
To: Lena Fischer <lena.fischer@acme-org.example>

We agreed the zephyrlabel pilot starts in the second week of April.
"""

TRANSCRIPT = """Meeting: Quokka handover
Customer: Acme Org (Grocery Retail, EMEA)
Date: 2025-04-02
Phase: Implementation
Attendees: Marco Rossi (RELEX), Lena Fischer (Acme)

Marco Rossi
0:100:10
MR
Marco Rossi 10 seconds
The quokkarollout depends on the new cold store.
Lena Fischer
0:200:20
LF
Lena Fischer 20 seconds
Understood, we will book the cold store.
"""

REPORT = """Subject: Weekly Acme update
From: Ana Duarte <ana.duarte@relexsolutions.example>
Date: Monday, May 5, 2025 17:30
To: Lena Fischer <lena.fischer@acme-org.example>

Update 05-05-2025 (Week 19)
On Track

Timeline
The wombatmigration is on plan.
"""


@pytest.fixture
def env(tmp_path):
    source = tmp_path / "source"
    for sub in ("emails", "transcripts", "reports"):
        (source / sub).mkdir(parents=True)
    (source / "emails" / "00_seed.txt").write_text(SEED_EMAIL, encoding="utf-8")
    db_path = tmp_path / "data" / "app.db"
    ops_dir = tmp_path / "data" / "privacy_ops"
    paths = upload.IngestPaths(
        source_dir=source,
        db_path=db_path,
        ops_dir=ops_dir,
        staging_root=tmp_path / "data" / "cache" / "uploads",
    )
    provider = {"value": MockEmbeddingProvider()}

    conn = connect(str(db_path))
    service.ingest(conn, source, provider["value"])
    conn.close()

    def get_conn():
        connection = connect(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[ingestion_api.get_paths] = lambda: paths
    app.dependency_overrides[deps.get_embedding_provider] = lambda: provider["value"]
    app.dependency_overrides[deps.get_conn] = get_conn
    yield TestClient(app), paths, provider, tmp_path
    app.dependency_overrides.clear()


def _post(client, files, document_type="email"):
    return client.post(
        "/api/ingest/upload",
        data={"document_type": document_type},
        files=[("files", (name, content, "text/plain")) for name, content in files],
    )


def _stats(client) -> dict:
    return client.get("/api/stats").json()


def _source_files(paths) -> set[str]:
    return {str(p.relative_to(paths.source_dir)) for p in paths.source_dir.rglob("*.txt")}


def test_valid_email_upload_is_persisted_and_ingested(env):
    client, paths, _, _ = env
    before = _stats(client)

    response = _post(client, [("zephyr-pilot.txt", EMAIL)])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ingested"
    assert body["uploaded_filenames"] == ["zephyr-pilot.txt"]
    assert body["documents_added"] == 1
    assert body["evidence_units_added"] == 1
    assert body["files"][0]["document_type"] == "EMAIL"
    assert body["files"][0]["evidence_units"] == 1
    assert (paths.source_dir / "emails" / "zephyr-pilot.txt").read_text(encoding="utf-8") == EMAIL
    after = _stats(client)
    assert after["documents"] == before["documents"] + 1
    assert after["evidence_units"] == before["evidence_units"] + 1
    assert body["fts_row_count"] == after["evidence_units"]


def test_valid_transcript_upload(env):
    client, paths, _, _ = env
    response = _post(client, [("quokka-handover.txt", TRANSCRIPT)], "transcript")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["files"][0]["document_type"] == "TRANSCRIPT"
    assert body["evidence_units_added"] == 2
    assert (paths.source_dir / "transcripts" / "quokka-handover.txt").is_file()


def test_valid_report_upload(env):
    client, paths, _, _ = env
    response = _post(client, [("weekly-may.txt", REPORT)], "report")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["files"][0]["document_type"] == "REPORT"
    assert body["evidence_units_added"] >= 1
    assert (paths.source_dir / "reports" / "weekly-may.txt").is_file()


def test_multiple_files_in_one_request(env):
    client, paths, _, _ = env
    other = EMAIL.replace("zephyrlabel", "narwhalcrate").replace("March 4", "March 5")
    response = _post(client, [("one.txt", EMAIL), ("two.txt", other)])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["documents_added"] == 2
    assert body["uploaded_filenames"] == ["one.txt", "two.txt"]
    assert {"emails/one.txt", "emails/two.txt"} <= _source_files(paths)


def test_invalid_extension_is_rejected_and_nothing_is_written(env):
    client, paths, _, _ = env
    before = _source_files(paths)
    response = _post(client, [("notes.pdf", EMAIL)])
    assert response.status_code == 400
    assert response.json()["status"] == "failed"
    assert "Only .txt" in response.json()["failures"][0]["error"]
    assert _source_files(paths) == before


def test_empty_file_is_rejected(env):
    client, paths, _, _ = env
    before = _source_files(paths)
    response = _post(client, [("blank.txt", "   \n\n")])
    assert response.status_code == 400
    assert "empty" in response.json()["failures"][0]["error"]
    assert _source_files(paths) == before


@pytest.mark.parametrize(
    "name",
    ["../evil.txt", "..\\evil.txt", "sub/evil.txt", "/etc/passwd.txt", ".hidden.txt", "a..b.txt"],
)
def test_unsafe_filenames_are_rejected(env, name):
    client, paths, _, tmp_path = env
    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    response = _post(client, [(name, EMAIL)])
    assert response.status_code == 400, response.text
    # Nothing was written anywhere, inside or outside the source tree.
    assert {p for p in tmp_path.rglob("*") if p.is_file()} == before


def test_one_bad_file_refuses_the_whole_batch(env):
    client, paths, _, _ = env
    before = _source_files(paths)
    response = _post(client, [("good.txt", EMAIL), ("bad.pdf", EMAIL)])
    assert response.status_code == 400
    assert _source_files(paths) == before


def test_duplicate_filename_never_overwrites(env):
    client, paths, _, _ = env
    first = _post(client, [("thread.txt", EMAIL)])
    assert first.status_code == 200, first.text
    changed = EMAIL.replace("zephyrlabel", "otterbarcode")
    second = _post(client, [("thread.txt", changed)])
    assert second.status_code == 200, second.text

    stored = second.json()["uploaded_filenames"][0]
    assert stored != "thread.txt" and stored.startswith("thread-")
    assert (paths.source_dir / "emails" / "thread.txt").read_text(encoding="utf-8") == EMAIL
    assert (paths.source_dir / "emails" / stored).read_text(encoding="utf-8") == changed
    ids = {f["document_id"] for f in first.json()["files"] + second.json()["files"]}
    assert len(ids) == 2


def test_same_name_as_a_document_in_another_folder_gets_a_new_name(env):
    client, paths, _, _ = env
    assert _post(client, [("shared.txt", EMAIL)]).status_code == 200
    response = _post(client, [("shared.txt", TRANSCRIPT)], "transcript")
    assert response.status_code == 200, response.text
    # A document id is its stem, so it must not repeat across folders.
    assert response.json()["uploaded_filenames"][0] != "shared.txt"


def test_ingestion_failure_does_not_report_success_and_removes_new_files(env, monkeypatch):
    client, paths, _, _ = env
    before_files = _source_files(paths)
    before = _stats(client)
    real_ingest = service.ingest
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real_ingest(*args, **kwargs)

    monkeypatch.setattr(service, "ingest", flaky)
    response = _post(client, [("zephyr-pilot.txt", EMAIL)])

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "failed"
    assert body["files_removed"] is True
    assert "RuntimeError" in body["detail"]
    assert "documents_added" not in body
    assert _source_files(paths) == before_files
    # The failed run's leftovers were rebuilt away: the archive is as it was.
    after = _stats(client)
    assert after["documents"] == before["documents"]
    assert after["evidence_units"] == before["evidence_units"]


def test_missing_document_after_ingestion_is_a_failure(env, monkeypatch):
    """ingest() returning without an exception is not proof: the database
    itself must contain the new document before success is reported."""
    client, paths, _, tmp_path = env
    before_files = _source_files(paths)
    real_ingest = service.ingest
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "emails").mkdir(parents=True)
    calls = {"n": 0}

    def ingest_that_ignores_the_upload(conn, source_dir, provider, **kwargs):
        calls["n"] += 1
        target = elsewhere if calls["n"] == 1 else source_dir
        return real_ingest(conn, target, provider, **kwargs)

    monkeypatch.setattr(service, "ingest", ingest_that_ignores_the_upload)
    response = _post(client, [("zephyr-pilot.txt", EMAIL)])

    assert response.status_code == 500
    assert response.json()["status"] == "failed"
    assert _source_files(paths) == before_files


def test_uploaded_evidence_is_searchable_through_fts(env):
    client, paths, _, _ = env
    assert _post(client, [("zephyr-pilot.txt", EMAIL)]).status_code == 200
    conn = connect(str(paths.db_path))
    try:
        hits = lexical.search(conn, "zephyrlabel pilot")
        assert hits
        row = conn.execute(
            "SELECT document_id, raw_text FROM evidence_units WHERE evidence_id = ?",
            (hits[0].evidence_id,),
        ).fetchone()
        assert row["document_id"] == "zephyr-pilot"
        assert "zephyrlabel" in row["raw_text"]
    finally:
        conn.close()


def test_stats_and_embeddings_grow_by_the_new_units(env):
    client, _, _, _ = env
    before = _stats(client)
    body = _post(client, [("quokka.txt", TRANSCRIPT)], "transcript").json()
    after = _stats(client)
    assert after["evidence_units"] == before["evidence_units"] + 2
    assert after["embeddings"] == before["embeddings"] + 2
    assert after["documents_by_type"]["TRANSCRIPT"] == 1
    assert body["embeddings"]["status"] == "complete"
    # Only the two new units needed the provider; the seed's vector was reused.
    assert body["embeddings"]["new_units_embedded"] == 2


def test_upload_without_a_provider_reports_skipped_and_keeps_old_vectors(env):
    client, paths, provider, _ = env
    provider["value"] = None
    before = _stats(client)
    assert before["embeddings"] == 1

    response = _post(client, [("zephyr-pilot.txt", EMAIL)])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["embeddings"]["status"] == "skipped"
    assert "skipped" in body["embeddings"]["message"]
    after = _stats(client)
    assert after["evidence_units"] == before["evidence_units"] + 1
    # Lexical-only ingestion must not destroy the semantic coverage that exists.
    assert after["embeddings"] == 1
    assert body["fts_row_count"] == after["evidence_units"]


def test_a_partial_embedding_failure_is_reported(env):
    client, _, provider, _ = env

    class Failing:
        model_name = MockEmbeddingProvider.model_name

        def embed_batch(self, texts):
            raise ValueError("bad response")

    provider["value"] = Failing()
    body = _post(client, [("zephyr-pilot.txt", EMAIL)]).json()
    assert body["status"] == "ingested"
    assert body["embeddings"]["status"] == "partial"
    assert body["embeddings"]["total_embeddings"] < body["embeddings"]["total_units"]


def test_wrong_document_type_content_is_rejected(env):
    client, paths, _, _ = env
    before = _source_files(paths)
    response = _post(client, [("actually-an-email.txt", EMAIL)], "transcript")
    assert response.status_code == 400
    assert "not a recognizable transcript" in response.json()["failures"][0]["error"]
    assert _source_files(paths) == before


def test_unknown_document_type_is_rejected(env):
    client, _, _, _ = env
    response = _post(client, [("x.txt", EMAIL)], "spreadsheet")
    assert response.status_code == 400


def test_too_many_files_and_oversized_files_are_rejected(env):
    client, paths, _, _ = env
    before = _source_files(paths)
    many = [(f"f{i}.txt", EMAIL) for i in range(upload.MAX_FILES + 1)]
    assert _post(client, many).status_code == 413

    huge = EMAIL + ("x" * (upload.MAX_FILE_BYTES + 10))
    response = _post(client, [("huge.txt", huge)])
    assert response.status_code == 400
    assert "larger than" in response.json()["failures"][0]["error"]
    assert _source_files(paths) == before


def test_binary_content_is_rejected(env):
    client, _, _, _ = env
    response = client.post(
        "/api/ingest/upload",
        data={"document_type": "email"},
        files=[("files", ("blob.txt", b"Subject: x\x00\xff\xfe", "text/plain"))],
    )
    assert response.status_code == 400


def test_upload_is_refused_while_a_privacy_operation_holds_the_lock(env):
    client, paths, _, _ = env
    ops.acquire(paths.ops_dir, "test-op")
    before = _source_files(paths)
    response = _post(client, [("zephyr-pilot.txt", EMAIL)])
    assert response.status_code == 503
    assert _source_files(paths) == before


def test_crlf_and_bom_uploads_are_normalized(env):
    client, paths, _, _ = env
    raw = ("﻿" + EMAIL.replace("\n", "\r\n")).encode("utf-8")
    response = client.post(
        "/api/ingest/upload",
        data={"document_type": "email"},
        files=[("files", ("windows.txt", raw, "text/plain"))],
    )
    assert response.status_code == 200, response.text
    stored = (paths.source_dir / "emails" / "windows.txt").read_bytes()
    assert not stored.startswith(b"\xef\xbb\xbf") and b"\r" not in stored


def test_staging_directory_is_cleaned_up(env):
    client, paths, _, _ = env
    assert _post(client, [("zephyr-pilot.txt", EMAIL)]).status_code == 200
    assert _post(client, [("bad.pdf", EMAIL)]).status_code == 400
    leftovers = [p for p in paths.staging_root.rglob("*") if p.is_file()]
    assert leftovers == []


def test_response_is_valid_json_with_the_documented_fields(env):
    client, _, _, _ = env
    body = json.loads(_post(client, [("zephyr-pilot.txt", EMAIL)]).text)
    assert {
        "status",
        "uploaded_filenames",
        "documents_added",
        "evidence_units_added",
        "fts_row_count",
        "embeddings",
        "parse_warnings",
    } <= set(body)
