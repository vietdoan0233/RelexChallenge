"""Risk routing -> Skeptic -> counter-retrieval -> reconciliation, end to end
through CaseService with a role-routed fake model and real retrieval."""

import json

import pytest

from app.core.errors import AnalysisUnavailableError
from app.reasoning.llm import RoleRoutedLLM
from app.reasoning.service import PROVISIONAL_NOTE, CaseService
from app.retrieval.service import RetrievalService


@pytest.fixture
def world(conn, seed_units):
    early = seed_units(
        conn,
        "meeting",
        [
            ("We agreed to build the message bus on Orion.", "Ana", "2025-01-10"),
            ("Orion message bus approved for the pilot.", "Marco", "2025-01-11"),
        ],
    )
    later = seed_units(
        conn,
        "ops",
        [
            (
                "We moved everything onto the Helios streaming platform after go-live; "
                "the previous broker is retired.",
                "Priya",
                "2025-09-01",
            )
        ],
        document_type="EMAIL",
        date="2025-09-01",
    )
    parking = seed_units(
        conn,
        "facilities",
        [
            ("Parking is on level two.", "Ana", "2025-01-10"),
            ("Parking passes are issued at reception.", "Lena", "2025-01-11"),
        ],
    )
    return early, later, parking


def _out(claims, summary="Orion was chosen.", status="SUPPORTED", **extra):
    return json.dumps({"answer_summary": summary, "status": status, "claims": claims, **extra})


def _claim(ids, text="Orion was chosen.", stance="AGREEMENT", confidence="HIGH", conflicts=()):
    return {
        "claim_text": text,
        "stance": stance,
        "confidence": confidence,
        "supporting_evidence_ids": list(ids),
        "conflicting_evidence_ids": list(conflicts),
    }


PLAN = json.dumps(
    {
        "weakest_claim": "Orion was chosen",
        "why_it_could_be_wrong": "a later platform move",
        "bundles": [{"strategy": "ALTERNATIVE_STATE", "queries": ["streaming platform"]}],
    }
)


def _service(conn, llm):
    return CaseService(conn, RetrievalService(conn, None), llm)


def test_low_risk_question_takes_the_single_pass_path(conn, world):
    _, _, parking = world
    llm = RoleRoutedLLM(
        {"PRIMARY": _out([_claim(parking, "Parking is on level two.", "STATUS_UPDATE")], "L2.")}
    )
    receipt, trace = _service(conn, llm).answer("Where is the parking?")
    assert llm.roles == ["PRIMARY"]
    assert receipt.review.risk_level == "LOW" and not receipt.review.skeptic_ran
    assert trace.skeptic_ran is False


def test_decision_question_runs_skeptic_and_reconciles_with_new_evidence(conn, world):
    early, later, _ = world
    verdict = json.dumps(
        {
            "objections": [
                {"text": "Superseded by a later move.", "severity": "HIGH", "evidence_ids": later}
            ]
        }
    )
    final = _out(
        [
            _claim(early, "Orion was agreed in January 2025.", "AGREEMENT", "HIGH"),
            _claim(
                later, "It was later retired for Helios.", "SUPERSEDED", "HIGH", conflicts=early
            ),
        ],
        "Orion was agreed but later superseded.",
        "CONFLICTING_EVIDENCE",
        conflict_resolution="The later platform move is stronger evidence of current state.",
    )
    llm = RoleRoutedLLM(
        {
            "PRIMARY": _out([_claim(early)]),
            "SKEPTIC_PLAN": PLAN,
            "SKEPTIC_VERDICT": verdict,
            "RECONCILE": final,
        }
    )
    receipt, trace = _service(conn, llm).answer("What message bus was agreed for the pilot?")

    assert llm.roles == ["PRIMARY", "SKEPTIC_PLAN", "SKEPTIC_VERDICT", "RECONCILE"]
    assert receipt.review.skeptic_ran and receipt.review.reconciled and receipt.review.completed
    assert receipt.review.risk_level in ("MEDIUM", "HIGH")
    assert later[0] in receipt.review.counter_evidence_ids
    # The reconciled answer may cite evidence only the Skeptic's retrieval surfaced.
    assert later[0] in [c.evidence_id for c in receipt.claims[1].support]
    assert receipt.claims[1].conflicts and receipt.conflict_resolution
    assert trace.counter_queries == 1 and later[0] in trace.counter_new_ids


def test_reconciliation_cannot_cite_evidence_nobody_saw(conn, world):
    early, _, parking = world
    llm = RoleRoutedLLM(
        {
            "PRIMARY": _out([_claim(early)]),
            "SKEPTIC_PLAN": PLAN,
            "SKEPTIC_VERDICT": json.dumps(
                {"objections": [{"text": "x", "severity": "LOW", "evidence_ids": ["EV-fake-1"]}]}
            ),
            # `parking` exists in the database but was never shown to any model.
            "RECONCILE": _out([_claim(early), _claim(parking, "Parking?")]),
        }
    )
    receipt, _ = _service(conn, llm).answer("What message bus was agreed for the pilot?")
    assert [c.claim_text for c in receipt.claims] == ["Orion was chosen."]
    assert receipt.validation.rejected_evidence_ids == parking
    assert receipt.review.objections[0].evidence_ids == []


def test_skeptic_failure_yields_a_provisional_answer_not_an_unchecked_confident_one(conn, world):
    early, *_ = world
    llm = RoleRoutedLLM(
        {"PRIMARY": _out([_claim(early)]), "SKEPTIC_PLAN": AnalysisUnavailableError("down")}
    )
    receipt, trace = _service(conn, llm).answer("What message bus was agreed for the pilot?")
    assert receipt.review.completed is False and trace.review_completed is False
    assert receipt.status == "PARTIALLY_SUPPORTED"
    assert all(c.confidence != "HIGH" for c in receipt.claims)
    assert PROVISIONAL_NOTE in receipt.missing_information


def test_reconcile_failure_after_objections_is_also_provisional(conn, world):
    early, later, _ = world
    llm = RoleRoutedLLM(
        {
            "PRIMARY": _out([_claim(early)]),
            "SKEPTIC_PLAN": PLAN,
            "SKEPTIC_VERDICT": json.dumps(
                {"objections": [{"text": "superseded", "severity": "HIGH", "evidence_ids": later}]}
            ),
            "RECONCILE": AnalysisUnavailableError("down"),
        }
    )
    receipt, _ = _service(conn, llm).answer("What message bus was agreed for the pilot?")
    assert receipt.review.completed is False
    assert receipt.review.objections and receipt.review.objections[0].text == "superseded"
    assert receipt.status == "PARTIALLY_SUPPORTED"


def test_counter_evidence_is_a_recorded_dependency_of_the_case(conn, world):
    early, later, _ = world
    llm = RoleRoutedLLM(
        {
            "PRIMARY": _out([_claim(early)]),
            "SKEPTIC_PLAN": PLAN,
            "SKEPTIC_VERDICT": json.dumps(
                {"objections": [{"text": "superseded", "severity": "HIGH", "evidence_ids": later}]}
            ),
            "RECONCILE": _out([_claim(early)]),
        }
    )
    receipt, _ = _service(conn, llm).answer("What message bus was agreed for the pilot?")
    rows = conn.execute(
        "SELECT evidence_id, usage FROM case_evidence WHERE case_id = ?", (receipt.case_id,)
    ).fetchall()
    assert (later[0], "CONFLICT") in [tuple(r) for r in rows]
    stored = conn.execute("SELECT receipt_json FROM cases").fetchone()[0]
    assert "streaming platform" not in stored  # ids only, no evidence text


def test_deleted_counter_evidence_disappears_from_the_served_review(conn, world):
    early, later, _ = world
    llm = RoleRoutedLLM(
        {
            "PRIMARY": _out([_claim(early)]),
            "SKEPTIC_PLAN": PLAN,
            "SKEPTIC_VERDICT": json.dumps(
                {"objections": [{"text": "superseded", "severity": "HIGH", "evidence_ids": later}]}
            ),
            "RECONCILE": _out([_claim(early)]),
        }
    )
    service = _service(conn, llm)
    receipt, _ = service.answer("What message bus was agreed for the pilot?")
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM evidence_units WHERE evidence_id = ?", (later[0],))
    served = service.get(receipt.case_id)
    assert later[0] not in served.review.counter_evidence_ids
    assert all(later[0] not in o.evidence_ids for o in served.review.objections)


def test_primary_failure_is_still_an_explicit_error(conn, world):
    llm = RoleRoutedLLM(
        {
            "PRIMARY": "garbage",
        }
    )
    with pytest.raises(AnalysisUnavailableError):
        _service(conn, llm).answer("Where is the parking?")


def test_no_matching_evidence_calls_no_model(conn, world):
    llm = RoleRoutedLLM({})
    receipt, _ = _service(conn, llm).answer("zzzqqq nonexistentterm")
    assert receipt.status == "INSUFFICIENT_EVIDENCE" and llm.roles == []


def test_units_merely_surfaced_by_the_search_are_not_recorded_as_dependencies(conn, world):
    early, later, _ = world
    llm = RoleRoutedLLM(
        {
            "PRIMARY": _out([_claim(early)]),
            "SKEPTIC_PLAN": PLAN,
            "SKEPTIC_VERDICT": json.dumps({"objections": []}),
        }
    )
    receipt, trace = _service(conn, llm).answer("What message bus was agreed for the pilot?")
    assert receipt.review.counter_units_examined >= 1  # the search did surface evidence
    assert receipt.review.counter_evidence_ids == []  # ...but the Skeptic relied on none
    used = conn.execute(
        "SELECT evidence_id FROM case_evidence WHERE case_id = ? AND usage = 'CONFLICT'",
        (receipt.case_id,),
    ).fetchall()
    assert used == []


def test_malformed_skeptic_verdict_marks_the_review_incomplete(conn, world):
    early, *_ = world
    llm = RoleRoutedLLM(
        {
            "PRIMARY": _out([_claim(early)]),
            "SKEPTIC_PLAN": PLAN,
            "SKEPTIC_VERDICT": json.dumps({"objections": "not a list"}),
        }
    )
    receipt, _ = _service(conn, llm).answer("What message bus was agreed for the pilot?")
    assert receipt.review.skeptic_ran and receipt.review.completed is False
    assert receipt.status == "PARTIALLY_SUPPORTED"
    assert receipt.review.reconciled is False


def test_invalid_primary_shape_is_an_error_when_evidence_exists(conn, world):
    bad = json.dumps({"claims": [[{"claim_text": "x"}]]})
    with pytest.raises(AnalysisUnavailableError):
        _service(conn, RoleRoutedLLM({"PRIMARY": bad})).answer("What message bus was agreed?")
