"""End-to-end Case flow over the HTTP API with a scripted model.

Every dependency that could reach the network or the repository's own
runtime database is overridden, so this is safe to run anywhere.
"""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.errors import AnalysisUnavailableError
from app.db import migrations
from app.db.connection import connect
from app.main import app
from app.reasoning.llm import ScriptedLLM


def _seed(db_path, seed_units):
    conn = connect(str(db_path))
    migrations.initialize(conn)
    ids = seed_units(
        conn,
        "meeting",
        [
            ("Shall bakery stay in the fresh workstream?", "Ana Duarte", "2025-01-10"),
            ("Yes.", "Lena Fischer", "2025-01-10"),
            ("Bakery is now its own workstream.", "Marco Rossi", "2025-06-10"),
        ],
    )
    conn.close()
    return ids


@pytest.fixture
def env(tmp_path, seed_units):
    db_path = tmp_path / "app.db"
    ids = _seed(db_path, seed_units)

    def get_conn():
        conn = connect(str(db_path))
        try:
            yield conn
        finally:
            conn.close()

    llm_holder = {"llm": None}
    app.dependency_overrides[deps.get_conn] = get_conn
    app.dependency_overrides[deps.get_llm] = lambda: llm_holder["llm"]
    app.dependency_overrides[deps.get_embedding_provider] = lambda: None
    app.dependency_overrides[deps.get_shared_index] = lambda: None
    yield TestClient(app), ids, llm_holder, db_path
    app.dependency_overrides.clear()


def _reply(claims, **extra):
    return json.dumps(
        {"answer_summary": "Bakery is separate.", "status": "SUPPORTED", "claims": claims, **extra}
    )


def _claim(ids):
    return {
        "claim_text": "Bakery became its own workstream.",
        "stance": "AGREEMENT",
        "confidence": "HIGH",
        "supporting_evidence_ids": ids,
    }


def test_query_returns_a_db_hydrated_case(env):
    client, ids, holder, _ = env
    holder["llm"] = ScriptedLLM([_reply([_claim([ids[2]])])])
    response = client.post("/api/cases/query", json={"query": "Is bakery in the fresh workstream?"})
    assert response.status_code == 200
    body = response.json()
    cite = body["claims"][0]["support"][0]
    assert cite["speaker_sender"] == "Marco Rossi"
    assert cite["event_date"] == "2025-06-10"
    assert cite["raw_text"] == "Bakery is now its own workstream."
    assert body["status"] == "SUPPORTED"
    assert body["validation"]["rejected_evidence_ids"] == []


def test_fabricated_id_never_renders(env):
    client, ids, holder, _ = env
    holder["llm"] = ScriptedLLM([_reply([_claim(["EV-meeting-99"])])])
    body = client.post("/api/cases/query", json={"query": "Is bakery in fresh?"}).json()
    assert body["claims"] == []
    assert body["status"] == "INSUFFICIENT_EVIDENCE"
    assert "EV-meeting-99" in body["validation"]["rejected_evidence_ids"]
    assert "EV-meeting-99" not in json.dumps(body["claims"])


def test_case_is_stored_with_ids_only_and_reloadable(env):
    client, ids, holder, db_path = env
    holder["llm"] = ScriptedLLM([_reply([_claim([ids[2]])])])
    body = client.post("/api/cases/query", json={"query": "Is bakery in fresh?"}).json()

    conn = sqlite3.connect(db_path)
    stored = conn.execute("SELECT receipt_json FROM cases").fetchone()[0]
    # A stored Case carries no evidence text: nothing personal is duplicated.
    assert "Bakery is now its own workstream." not in stored
    usage = conn.execute("SELECT evidence_id, usage FROM case_evidence").fetchall()
    assert (ids[2], "SUPPORT") in usage
    conn.close()

    again = client.get(f"/api/cases/{body['case_id']}").json()
    assert again["claims"][0]["support"][0]["raw_text"] == "Bakery is now its own workstream."


def test_deleted_evidence_disappears_from_a_stored_case(env):
    client, ids, holder, db_path = env
    holder["llm"] = ScriptedLLM([_reply([_claim([ids[2]])])])
    case_id = client.post("/api/cases/query", json={"query": "Is bakery in fresh?"}).json()[
        "case_id"
    ]
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM evidence_units WHERE evidence_id = ?", (ids[2],))
    conn.commit()
    conn.close()
    body = client.get(f"/api/cases/{case_id}").json()
    assert body["claims"] == []
    assert body["status"] == "INSUFFICIENT_EVIDENCE"


def test_no_matching_evidence_skips_the_model_entirely(env):
    client, _ids, holder, _ = env
    llm = ScriptedLLM([_reply([])])
    holder["llm"] = llm
    body = client.post("/api/cases/query", json={"query": "zzzqqq nonexistentterm"}).json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE"
    assert llm.calls == 0


def test_model_failure_is_an_explicit_503_not_an_invented_answer(env):
    client, _ids, holder, _ = env

    class Broken:
        model_name = "x"

        def complete_json(self, *, system, user):
            raise AnalysisUnavailableError("down")

    holder["llm"] = Broken()
    response = client.post("/api/cases/query", json={"query": "Is bakery in fresh?"})
    assert response.status_code == 503
    assert "claims" not in response.json()


def test_unconfigured_model_is_a_503(env):
    client, *_ = env
    assert client.post("/api/cases/query", json={"query": "Is bakery in fresh?"}).status_code == 503


def test_query_validation(env):
    client, *_ = env
    assert client.post("/api/cases/query", json={"query": "hi"}).status_code == 422
    assert client.post("/api/cases/query", json={"query": "x" * 2000}).status_code == 422


def test_unknown_case_and_evidence_are_404(env):
    client, *_ = env
    assert client.get("/api/cases/nope").status_code == 404
    assert client.get("/api/evidence/EV-nope").status_code == 404


def test_evidence_endpoint_returns_highlighted_unit_with_neighbours(env):
    client, ids, *_ = env
    body = client.get(f"/api/evidence/{ids[1]}").json()
    assert body["citation"]["raw_text"] == "Yes."
    assert [c["evidence_id"] for c in body["context_before"]] == [ids[0]]
    assert [c["evidence_id"] for c in body["context_after"]] == [ids[2]]


def test_stats_are_counts_only(env):
    client, ids, holder, _ = env
    body = client.get("/api/stats").json()
    assert body["documents"] == 1 and body["evidence_units"] == 3
    assert body["first_date"] and body["last_date"]
    # Nothing textual about the evidence or anyone in it.
    assert "Ana Duarte" not in json.dumps(body) and "bakery" not in json.dumps(body).lower()


def test_recent_cases_lists_newest_first_and_hides_radar_cases(env):
    client, ids, holder, db_path = env
    holder["llm"] = ScriptedLLM([_reply([_claim([ids[2]])])])
    first = client.post(
        "/api/cases/query", json={"query": "Is bakery in the fresh workstream?"}
    ).json()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO cases VALUES ('radar-1', 'Reconsideration: some idea', '{}', "
        "'2999-01-01T00:00:00+00:00', 't')"
    )
    conn.commit()
    conn.close()
    listed = client.get("/api/cases").json()
    assert [c["case_id"] for c in listed] == [first["case_id"]]
    assert listed[0]["status"] == "SUPPORTED" and listed[0]["claims"] == 1
    assert client.get("/api/cases?limit=0").status_code == 200


def test_recent_cases_lists_a_repeated_question_once_with_its_latest_case(env):
    client, ids, holder, _ = env
    holder["llm"] = ScriptedLLM([_reply([_claim([ids[2]])])])
    first = client.post(
        "/api/cases/query", json={"query": "Is bakery in the fresh workstream?"}
    ).json()
    second = client.post(
        "/api/cases/query", json={"query": "is  bakery in the FRESH workstream?"}
    ).json()
    listed = client.get("/api/cases").json()
    assert len(listed) == 1 and listed[0]["case_id"] == second["case_id"]
    assert first["case_id"] != second["case_id"]
