"""Reconsideration Radar, end to end with a role-routed fake model and real
retrieval. Covers the docs/RECONSIDERATION_RADAR.md exit criteria."""

import json

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.db import migrations
from app.db.connection import connect
from app.main import app
from app.radar import guard, service
from app.radar.schemas import Assessment, AssessmentOut, CheckResult, RadarVerdict
from app.reasoning.llm import RoleRoutedLLM
from app.retrieval.service import RetrievalService


@pytest.fixture
def world(conn, seed_units):
    planning = seed_units(
        conn,
        "planning",
        [
            ("Ana proposed adding streaming ingest for real time waste data.", "Ana", "2025-01-10"),
            (
                "We cannot do that now, the team has no capacity until the migration finishes.",
                "Marco",
                "2025-01-10",
            ),
            ("So we defer streaming ingest until the migration is done.", "Lena", "2025-01-11"),
        ],
    )
    later = seed_units(
        conn,
        "later",
        [
            (
                "The migration finished in August and two engineers are now free.",
                "Priya",
                "2025-09-02",
            )
        ],
        document_type="EMAIL",
        date="2025-09-02",
    )
    against = seed_units(
        conn,
        "plan-2026",
        [("Streaming ingest is not on the plan for this year.", "Ana", "2025-11-05")],
        date="2025-11-05",
    )
    return planning, later, against


def _candidate(planning, **overrides):
    base = {
        "proposal": "Add streaming ingest for real time waste data",
        "outcome": "DEFERRED",
        "blocker": "The team had no capacity until the migration finished",
        "blocker_category": "CAPACITY_EFFORT",
        "monitorable_condition": "Migration finished and engineers are free",
        "proposal_evidence_ids": [planning[0]],
        "outcome_evidence_ids": [planning[2]],
        "blocker_evidence_ids": [planning[1]],
    }
    base.update(overrides)
    return base


def _assess(later, **overrides):
    base = {
        "changed_condition": "The migration that blocked the work has finished.",
        "internal_change_evidence_ids": later,
        "external_signal_ids": [],
        "current_state_evidence_ids": [],
        "assessment": "WORTH_REASSESSING",
        "assessment_rationale": "The stated capacity blocker may have lapsed.",
        "unestablished": ["Whether the freed engineers are assigned elsewhere."],
        "next_check": "Ask the delivery lead whether the engineers are still unassigned.",
    }
    base.update(overrides)
    return base


def _checks(**failed):
    checks = []
    for n in range(1, 8):
        spec = failed.get(f"c{n}", (True, True))
        checks.append(
            {
                "check": n,
                "answered": spec[0],
                "passed": spec[1] if spec[0] else None,
                "note": f"check {n}",
                "evidence_ids": [],
            }
        )
    return checks


PLAN = json.dumps(
    {
        "weakest_claim": "blocker lapsed",
        "why_it_could_be_wrong": "still busy",
        "bundles": [{"strategy": "LATER_IMPLEMENTATION", "queries": ["streaming ingest plan"]}],
    }
)


def _llm(candidates, assess, verdict=None):
    return RoleRoutedLLM(
        {
            "RADAR_DISCOVER": json.dumps({"candidates": candidates}),
            "RADAR_ASSESS": assess if isinstance(assess, str) else json.dumps(assess),
            "SKEPTIC_PLAN": PLAN,
            "RADAR_SKEPTIC": verdict or json.dumps({"checks": _checks()}),
        }
    )


def _run(conn, llm, tmp_path, limit=5):
    return service.run_radar(conn, RetrievalService(conn, None), llm, tmp_path, limit=limit)


def _rows(conn):
    return conn.execute("SELECT * FROM pulse_findings").fetchall()


def test_a_surfaced_finding_is_backed_by_a_validated_case_and_evidence(conn, world, tmp_path):
    planning, later, _ = world
    result = _run(conn, _llm([_candidate(planning)], _assess(later)), tmp_path)
    assert len(result.surfaced) == 1
    (row,) = _rows(conn)
    assert row["category"] == "RECONSIDERATION_CANDIDATE" and row["status"] == "WORTH_REASSESSING"

    stored = json.loads(row["finding_json"])
    # Ids only: no evidence text is duplicated into the finding.
    verbatim = "We cannot do that now, the team has no capacity until the migration finishes."
    assert verbatim not in row["finding_json"]
    case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (stored["case_id"],)).fetchone()
    assert case is not None
    linked = {
        r[0]
        for r in conn.execute(
            "SELECT evidence_id FROM finding_evidence WHERE finding_id = ?", (row["finding_id"],)
        )
    }
    assert set(planning) <= linked and later[0] in linked

    (card,) = service.load_findings(conn, tmp_path)
    assert card.proposal_citations[0].raw_text.startswith("Ana proposed")
    assert card.blocker_citations[0].speaker_sender == "Marco"
    assert card.internal_change_citations[0].evidence_id == later[0]
    assert card.external_signals == []  # lenses stay separate: nothing external was invented
    # Missing budget/owner/approval is always shown when a change is claimed.
    assert any("budget" in m.lower() for m in card.unestablished)


def test_language_stronger_than_worth_reassessing_is_withheld(conn, world, tmp_path):
    planning, later, _ = world
    llm = _llm(
        [_candidate(planning)],
        _assess(
            later,
            assessment_rationale="We recommend the team should pursue this now.",
            next_check="You should approve funding immediately.",
        ),
    )
    _run(conn, llm, tmp_path)
    (card,) = service.load_findings(conn, tmp_path)
    assert card.assessment_rationale == guard.WITHHELD and card.next_check == guard.WITHHELD
    stored = json.loads(_rows(conn)[0]["finding_json"])
    assert "overreaching wording was withheld" in stored["notes"]


@pytest.mark.parametrize(
    "text",
    [
        "We should pursue this",
        "This is now approved",
        "I recommend reopening it",
        "It is strategically the right move",
        "give it the green light",
    ],
)
def test_the_overreach_detector_catches_stronger_wording(text):
    assert guard.is_overreach(text)


@pytest.mark.parametrize(
    "text",
    [
        "It may be worth reassessing.",
        "The blocker may have changed.",
        "Ask who owns it.",
        "No internal evidence establishes a budget, an owner, or an approval to reopen this idea.",
        "Whether the budget was approved is not established.",
    ],
)
def test_the_overreach_detector_allows_bounded_wording(text):
    assert not guard.is_overreach(text)


def test_a_changed_condition_without_a_receipt_is_lowered(conn, world, tmp_path):
    planning, _, _ = world
    _run(
        conn, _llm([_candidate(planning)], _assess([], external_signal_ids=["sig-fake"])), tmp_path
    )
    assert _rows(conn)[0]["status"] == "INSUFFICIENT_EVIDENCE"


def test_the_skeptic_can_reject_a_false_candidate(conn, world, tmp_path):
    planning, later, _ = world
    verdict = json.dumps(
        {
            "checks": _checks(c1=(True, False)),
            "reject_candidate": True,
            "reject_reason": "It was agreed, not rejected.",
        }
    )
    result = _run(conn, _llm([_candidate(planning)], _assess(later), verdict), tmp_path)
    assert result.surfaced == [] and _rows(conn) == []
    assert result.rejected and "check 1" in result.rejected[0][1]


def test_an_obsolete_candidate_is_rejected_by_check_seven(conn, world, tmp_path):
    planning, later, _ = world
    verdict = json.dumps({"checks": _checks(c7=(True, False))})
    result = _run(conn, _llm([_candidate(planning)], _assess(later), verdict), tmp_path)
    assert result.surfaced == [] and result.rejected


def test_a_change_that_does_not_address_the_blocker_is_only_partial(conn, world, tmp_path):
    planning, later, _ = world
    verdict = json.dumps({"checks": _checks(c4=(True, False))})
    _run(conn, _llm([_candidate(planning)], _assess(later), verdict), tmp_path)
    assert _rows(conn)[0]["status"] == "PARTIALLY_CHANGED"


def test_recent_internal_evidence_against_reopening_keeps_it_blocked(conn, world, tmp_path):
    planning, later, against = world
    verdict = json.dumps({"checks": _checks(c6=(True, False))})
    _run(
        conn,
        _llm([_candidate(planning)], _assess(later, current_state_evidence_ids=against), verdict),
        tmp_path,
    )
    assert _rows(conn)[0]["status"] == "STILL_BLOCKED"


def test_an_unanswerable_check_is_shown_as_missing_information(conn, world, tmp_path):
    planning, later, _ = world
    verdict = json.dumps({"checks": _checks(c5=(False, None))})
    _run(conn, _llm([_candidate(planning)], _assess(later), verdict), tmp_path)
    (card,) = service.load_findings(conn, tmp_path)
    assert any("check 5 could not be answered" in m for m in card.unestablished)


def test_candidates_without_real_evidence_are_dropped_not_softened(conn, world, tmp_path):
    planning, later, _ = world
    candidates = [
        _candidate(
            planning, blocker_evidence_ids=["EV-invented-1"], proposal="No blocker evidence"
        ),
        _candidate(planning, proposal="Fabricated proposal ids", proposal_evidence_ids=["EV-x"]),
        _candidate(planning),
    ]
    result = _run(conn, _llm(candidates, _assess(later)), tmp_path)
    assert result.dropped_unsupported == 2 and len(result.surfaced) == 1


def test_duplicates_and_the_limit_are_respected(conn, world, tmp_path):
    planning, later, _ = world
    dup = [
        _candidate(planning),
        _candidate(planning),
        _candidate(planning, proposal="A second, different idea"),
    ]
    result = _run(conn, _llm(dup, _assess(later)), tmp_path, limit=1)
    assert len(result.surfaced) == 1


def test_external_signals_are_curated_validated_and_kept_separate(conn, world, tmp_path):
    planning, later, _ = world
    (tmp_path / "external_signals.json").write_text(
        json.dumps(
            {
                "signals": [
                    {
                        "signal_id": "sig-1",
                        "title": "A vendor update",
                        "source": "Vendor blog",
                        "published": "2025-08-01",
                        "url": "https://example.test/a",
                        "summary": "Adds a feature.",
                        "categories": ["CAPACITY_EFFORT"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _run(
        conn,
        _llm([_candidate(planning)], _assess([], external_signal_ids=["sig-1", "sig-invented"])),
        tmp_path,
    )
    (card,) = service.load_findings(conn, tmp_path)
    assert [s.signal_id for s in card.external_signals] == ["sig-1"]
    assert card.internal_change_citations == []
    # External-only: the card must say the organization's own position is unknown.
    assert any("current position" in m for m in card.unestablished)


def test_a_malformed_signal_file_fails_loudly(conn, world, tmp_path):
    (tmp_path / "external_signals.json").write_text("{not json", encoding="utf-8")
    planning, later, _ = world
    with pytest.raises(ValueError):
        _run(conn, _llm([_candidate(planning)], _assess(later)), tmp_path)


def test_rerunning_replaces_earlier_findings_and_their_cases(conn, world, tmp_path):
    planning, later, _ = world
    llm = lambda: _llm([_candidate(planning)], _assess(later))  # noqa: E731
    _run(conn, llm(), tmp_path)
    _run(conn, llm(), tmp_path)
    assert len(_rows(conn)) == 1
    assert conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 1


def test_a_finding_whose_evidence_was_removed_is_no_longer_shown(conn, world, tmp_path):
    planning, later, _ = world
    _run(conn, _llm([_candidate(planning)], _assess(later)), tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM evidence_units WHERE evidence_id = ?", (planning[1],))
    assert service.load_findings(conn, tmp_path) == []


def test_a_failed_model_call_surfaces_nothing_rather_than_something_invented(conn, world, tmp_path):
    planning, later, _ = world
    llm = _llm([_candidate(planning)], "not json at all")
    result = _run(conn, llm, tmp_path)
    assert result.surfaced == [] and _rows(conn) == []


def test_guard_finalize_directly():
    assessed = AssessmentOut(
        assessment=Assessment.WORTH_REASSESSING, assessment_rationale="r", next_check="n"
    )
    verdict = RadarVerdict(checks=[CheckResult(check=3, answered=False, note="unclear")])
    final, missing, _ = guard.finalize(assessed, verdict, valid_internal=["EV-1"], valid_signals=[])
    assert final == Assessment.WORTH_REASSESSING
    assert any("check 3" in m for m in missing) and guard.DEFAULT_UNESTABLISHED in missing


# ----------------------------------------------------------------- API


def test_api_serves_precomputed_findings_and_404s(world, tmp_path, monkeypatch, seed_units):
    from app.core import config

    db_path = tmp_path / "app.db"
    conn = connect(str(db_path))
    migrations.initialize(conn)
    planning = seed_units(
        conn,
        "planning",
        [
            ("Ana proposed streaming ingest.", "Ana", "2025-01-10"),
            ("No capacity until the migration finishes.", "Marco", "2025-01-10"),
            ("So we defer streaming ingest.", "Lena", "2025-01-11"),
        ],
    )
    later = seed_units(
        conn,
        "later",
        [("The migration finished in August.", "Priya", "2025-09-02")],
        date="2025-09-02",
    )
    _run(conn, _llm([_candidate(planning)], _assess(later)), tmp_path)
    conn.close()

    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SOURCE_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    app.dependency_overrides[deps.get_conn] = lambda: (yield connect(str(db_path)))  # type: ignore[misc]

    def get_conn():
        c = connect(str(db_path))
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[deps.get_conn] = get_conn
    try:
        client = TestClient(app)
        cards = client.get("/api/radar").json()
        assert len(cards) == 1 and cards[0]["assessment"] == "WORTH_REASSESSING"
        assert cards[0]["proposal_citations"][0]["raw_text"] == "Ana proposed streaming ingest."
        assert client.get(f"/api/radar/{cards[0]['finding_id']}").status_code == 200
        assert client.get("/api/radar/RC-nope").status_code == 404
        # The linked Case opens through the ordinary Case endpoint.
        assert client.get(f"/api/cases/{cards[0]['case_id']}").status_code == 200
    finally:
        app.dependency_overrides.clear()
        config.get_settings.cache_clear()


# ------------------------------------------------------------- deletion


def test_deleting_a_person_invalidates_their_findings_and_linked_cases(tmp_path):
    from test_privacy_purge import Instance

    inst = Instance(tmp_path)
    try:
        kwame = [i for i, r in inst.units().items() if r["speaker_sender"] == "Kwame Boateng"]
        other = [i for i, r in inst.units().items() if r["speaker_sender"] == "Lena Fischer"]
        for label, ids in (("kwame", kwame[:1]), ("other", other[:1])):
            case_id = f"case-{label}"
            inst.conn.execute("INSERT INTO cases VALUES (?, 'q', '{}', 't', 't')", (case_id,))
            inst.conn.execute(
                "INSERT INTO case_evidence VALUES (?, ?, 'SUPPORT')", (case_id, ids[0])
            )
            inst.conn.execute(
                "INSERT INTO pulse_findings VALUES (?, 'RECONSIDERATION_CANDIDATE', 't', 's', "
                "'STILL_BLOCKED', ?, 't')",
                (f"RC-{label}", json.dumps({"case_id": case_id})),
            )
            inst.conn.execute("INSERT INTO finding_evidence VALUES (?, ?)", (f"RC-{label}", ids[0]))
        inst.conn.commit()

        preview = __import__("app.privacy.service", fromlist=["x"]).preview(
            inst.conn, inst.source, "kwame-boateng"
        )
        assert preview.findings_to_invalidate == 1

        result = inst.purge()
        assert result.findings_invalidated == 1
        findings = {r[0] for r in inst.conn.execute("SELECT finding_id FROM pulse_findings")}
        cases = {r[0] for r in inst.conn.execute("SELECT case_id FROM cases")}
        assert findings == {"RC-other"} and cases == {"case-other"}
    finally:
        inst.conn.close()


def test_a_finding_whose_prose_names_the_person_is_invalidated_even_if_it_cites_nothing_changed(
    tmp_path,
):
    from test_privacy_purge import Instance

    inst = Instance(tmp_path)
    try:
        inst.conn.execute(
            "INSERT INTO pulse_findings VALUES ('RC-prose', 'RECONSIDERATION_CANDIDATE', "
            "'Kwame Boateng idea', 's', 'STILL_BLOCKED', '{}', 't')"
        )
        inst.conn.commit()
        inst.purge()
        assert inst.conn.execute("SELECT COUNT(*) FROM pulse_findings").fetchone()[0] == 0
    finally:
        inst.conn.close()


def test_a_skeptic_that_skips_checks_one_and_seven_cannot_wave_a_candidate_through(
    conn, world, tmp_path
):
    planning, later, _ = world
    only_middle = json.dumps({"checks": [c for c in _checks() if c["check"] in (2, 3, 4, 5, 6)]})
    _run(conn, _llm([_candidate(planning)], _assess(later), only_middle), tmp_path)
    (card,) = service.load_findings(conn, tmp_path)
    assert {c.check for c in card.checks} == {1, 2, 3, 4, 5, 6, 7}
    assert sum(1 for m in card.unestablished if "did not evaluate" in m) == 2


def test_the_monitorable_condition_is_held_to_the_same_bounded_voice(conn, world, tmp_path):
    planning, later, _ = world
    cand = _candidate(planning, monitorable_condition="The team should now go ahead and fund it")
    _run(conn, _llm([cand], _assess(later)), tmp_path)
    (card,) = service.load_findings(conn, tmp_path)
    assert card.monitorable_condition == guard.WITHHELD


def test_evidence_ids_never_appear_in_the_radars_prose(conn, world, tmp_path):
    planning, later, _ = world
    assess = _assess(
        later,
        assessment_rationale=f"Migration ended [{later[0]}]; capacity may exist ({planning[1]}).",
        changed_condition=f"Engineers freed [{later[0]}].",
        next_check=f"Ask whether {later[0]} still holds.",
        unestablished=[f"Owner unknown [{planning[0]}]."],
    )
    _run(conn, _llm([_candidate(planning)], assess), tmp_path)
    (card,) = service.load_findings(conn, tmp_path)
    prose = [
        card.assessment_rationale,
        card.changed_condition or "",
        card.next_check,
        *card.unestablished,
    ]
    assert not any("EV-" in text for text in prose)


def test_an_overreaching_missing_information_line_is_dropped_not_shown_as_a_fact(
    conn, world, tmp_path
):
    planning, later, _ = world
    assess = _assess(
        later, unestablished=["We should fund it now", "Who owns delivery is unknown."]
    )
    _run(conn, _llm([_candidate(planning)], assess), tmp_path)
    (card,) = service.load_findings(conn, tmp_path)
    assert guard.WITHHELD not in card.unestablished
    assert "Who owns delivery is unknown." in card.unestablished
    assert not any("fund it" in m for m in card.unestablished)
