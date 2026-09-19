import pytest

from app.reasoning import risk
from app.reasoning.evidence import EvidenceSet
from app.retrieval.service import RetrievalService
from app.schemas.reasoning import PrimaryOutput


@pytest.fixture
def corpus(conn, seed_units):
    a = seed_units(
        conn,
        "meeting",
        [
            ("Parking is on level two.", "Ana", "2025-01-10"),
            ("Parking passes are issued at reception.", "Lena", "2025-01-11"),
        ],
        document_type="TRANSCRIPT",
    )
    later = seed_units(
        conn,
        "status",
        [("Parking moved to level three.", "Marco", "2025-09-10")],
        document_type="REPORT",
    )
    return a, later


def _output(claims, status="SUPPORTED"):
    return PrimaryOutput.model_validate({"answer_summary": "s", "status": status, "claims": claims})


def _claim(support, *, stance="STATUS_UPDATE", confidence="HIGH", conflicts=()):
    return {
        "claim_text": "c",
        "stance": stance,
        "confidence": confidence,
        "supporting_evidence_ids": list(support),
        "conflicting_evidence_ids": list(conflicts),
    }


def _assess(conn, query, output, temporal=False):
    retrieval = RetrievalService(conn, None).retrieve(query, temporal_sweep=temporal)
    return risk.assess(query, output, retrieval, EvidenceSet.from_results(retrieval))


def test_plain_well_supported_lookup_is_low_risk(conn, corpus):
    a, _ = corpus
    out = _output([_claim(a)])
    result = _assess(conn, "Where is parking?", out)
    assert result.triggers == [] and result.level == "LOW" and not result.deep_check


@pytest.mark.parametrize(
    "query",
    [
        "What did they agree about parking?",
        "Who decided parking?",
        "Who approved the parking change?",
        "Was parking signed off?",
        "Is parking currently on level two?",
        "Was parking superseded?",
        "Who proposed the parking change?",
        "Was the parking commitment fulfilled?",
    ],
)
def test_decision_and_current_state_questions_force_deep_checking(conn, corpus, query):
    a, _ = corpus
    # Even a HIGH-confidence, well-supported answer must not waive the check.
    result = _assess(conn, query, _output([_claim(a)]))
    assert result.deep_check
    assert any(t.startswith("query:") for t in result.triggers)


def test_single_supporting_unit_triggers(conn, corpus):
    a, _ = corpus
    assert (
        "a claim rests on a single supporting unit"
        in _assess(conn, "Where is parking?", _output([_claim(a[:1])])).triggers
    )


def test_medium_confidence_ambiguous_stance_conflict_and_status_trigger(conn, corpus):
    a, later = corpus
    triggers = _assess(
        conn,
        "Where is parking?",
        _output(
            [_claim(a, stance="PROPOSAL", confidence="MEDIUM", conflicts=later)],
            status="CONFLICTING_EVIDENCE",
        ),
    ).triggers
    assert "a claim has medium or low confidence" in triggers
    assert "stance is ambiguous (proposal, assumption, uncertain, or superseded)" in triggers
    assert "conflicting evidence was cited" in triggers
    assert "model status is CONFLICTING_EVIDENCE" in triggers


def test_material_date_spread_and_report_vs_other_sources_trigger(conn, corpus):
    a, later = corpus
    triggers = _assess(conn, "Where is parking?", _output([_claim([a[0], later[0]])])).triggers
    assert "supporting evidence spans materially different dates" in triggers
    assert "a status report is set against other evidence" in triggers


def test_source_types_that_disagree_trigger(conn, corpus):
    a, later = corpus
    triggers = _assess(conn, "Where is parking?", _output([_claim(a, conflicts=later)])).triggers
    assert "source types disagree" in triggers


def test_later_relevant_evidence_triggers(conn, corpus):
    a, _ = corpus
    result = _assess(conn, "Where is parking?", _output([_claim(a)]), temporal=True)
    assert "later relevant evidence exists" in result.triggers


def test_no_claims_triggers_and_three_triggers_is_high(conn, corpus):
    assert "no claim was produced" in _assess(conn, "Where is parking?", _output([])).triggers
    a, later = corpus
    high = _assess(
        conn,
        "Who decided the current parking?",
        _output([_claim(a, confidence="LOW", conflicts=later)]),
    )
    assert high.level == "HIGH"
