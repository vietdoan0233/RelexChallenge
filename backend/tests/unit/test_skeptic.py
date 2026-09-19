import json

import pytest

from app.core.errors import AnalysisUnavailableError
from app.reasoning import skeptic
from app.reasoning.evidence import EvidenceSet
from app.reasoning.llm import RoleRoutedLLM
from app.retrieval.service import RetrievalService
from app.schemas.reasoning import PrimaryOutput


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
    # No word in common with the question and no explicit "rejected": only
    # a search for the replacement or later state can find this.
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
    return early, later


def _candidate(early):
    return PrimaryOutput.model_validate(
        {
            "answer_summary": "Orion was chosen.",
            "status": "SUPPORTED",
            "claims": [
                {
                    "claim_text": "Orion message bus was chosen.",
                    "stance": "AGREEMENT",
                    "confidence": "HIGH",
                    "supporting_evidence_ids": early,
                }
            ],
        }
    )


def _plan(*bundles):
    return json.dumps(
        {"weakest_claim": "w", "why_it_could_be_wrong": "y", "bundles": list(bundles)}
    )


def _run(conn, llm, early):
    service = RetrievalService(conn, None)
    retrieval = service.retrieve("What message bus was agreed for the pilot?")
    evidence = EvidenceSet.from_results(retrieval)
    return skeptic.run(llm, service, "What message bus was agreed?", _candidate(early), evidence)


def test_direct_negation_search_alone_would_miss_the_replacement(conn, world):
    early, later = world
    service = RetrievalService(conn, None)
    result = service.retrieve("Orion message bus rejected")
    assert later[0] not in result.visible_evidence_ids


def test_skeptic_finds_indirect_replacement_with_different_vocabulary(conn, world):
    early, later = world
    llm = RoleRoutedLLM(
        {
            "SKEPTIC_PLAN": _plan(
                {
                    "strategy": "ALTERNATIVE_STATE",
                    "queries": ["streaming platform", "previous broker"],
                }
            ),
            "SKEPTIC_VERDICT": json.dumps(
                {
                    "objections": [
                        {
                            "text": "A later move to another platform supersedes it.",
                            "severity": "HIGH",
                            "evidence_ids": later,
                        }
                    ]
                }
            ),
        }
    )
    result = _run(conn, llm, early)
    assert later[0] in result.new_evidence_ids
    assert result.has_findings and result.objections[0].evidence_ids == later
    assert result.queries_run == 2
    assert llm.roles == ["SKEPTIC_PLAN", "SKEPTIC_VERDICT"]


def test_new_counter_evidence_is_marked_for_the_verdict_step(conn, world):
    early, later = world
    seen = {}

    def verdict(system, user):
        seen["user"] = user
        return json.dumps({"objections": []})

    llm = RoleRoutedLLM(
        {
            "SKEPTIC_PLAN": _plan(
                {"strategy": "LATER_IMPLEMENTATION", "queries": ["streaming platform"]}
            ),
            "SKEPTIC_VERDICT": verdict,
        }
    )
    _run(conn, llm, early)
    assert f"![{later[0]}]" in seen["user"]


def test_bundles_and_queries_are_capped(conn, world):
    early, _ = world
    big = {"strategy": "DIRECT_CONTRADICTION", "queries": ["a1", "a2", "a3", "a4", "a5"]}
    llm = RoleRoutedLLM(
        {"SKEPTIC_PLAN": _plan(big, big, big), "SKEPTIC_VERDICT": json.dumps({"objections": []})}
    )
    result = _run(conn, llm, early)
    assert result.queries_run <= skeptic.MAX_BUNDLES * skeptic.MAX_QUERIES_PER_BUNDLE


def test_no_new_evidence_skips_the_verdict_call(conn, world):
    early, _ = world
    llm = RoleRoutedLLM(
        {"SKEPTIC_PLAN": _plan({"strategy": "DIRECT_CONTRADICTION", "queries": ["zzzqqq nothing"]})}
    )
    result = _run(conn, llm, early)
    assert not result.has_findings
    assert llm.roles == ["SKEPTIC_PLAN"]


def test_unusable_plan_is_a_controlled_error(conn, world):
    early, _ = world
    with pytest.raises(AnalysisUnavailableError) as info:
        _run(conn, RoleRoutedLLM({"SKEPTIC_PLAN": "not json leaky-text"}), early)
    assert "leaky" not in str(info.value)


def test_alternative_and_later_strategies_use_the_temporal_sweep(conn, world):
    early, _ = world
    service = RetrievalService(conn, None)
    flags = []
    original = service.retrieve

    def spy(query, *, temporal_sweep=None):
        flags.append(temporal_sweep)
        return original(query, temporal_sweep=temporal_sweep)

    service.retrieve = spy
    llm = RoleRoutedLLM(
        {
            "SKEPTIC_PLAN": _plan(
                {"strategy": "DIRECT_CONTRADICTION", "queries": ["rejected"]},
                {"strategy": "ALTERNATIVE_STATE", "queries": ["platform"]},
            ),
            "SKEPTIC_VERDICT": json.dumps({"objections": []}),
        }
    )
    retrieval = original("message bus")
    skeptic.run(llm, service, "q", _candidate(early), EvidenceSet.from_results(retrieval))
    assert flags == [False, True]


def test_counter_search_contribution_is_bounded(conn, seed_units):
    seed_units(conn, "big", [f"alpha topic unit {i} with several words here." for i in range(60)])
    service = RetrievalService(conn, None)
    evidence = EvidenceSet()
    new = evidence.add(
        service.retrieve("alpha topic", temporal_sweep=False),
        top_hits=skeptic._COUNTER_TOP_HITS,
        top_later=skeptic._COUNTER_TOP_LATER,
    )
    # 5 hits plus their +-1 windows at most: far below the unbounded ~40.
    assert 0 < len(new) <= skeptic._COUNTER_TOP_HITS * 3


def test_malformed_verdict_shape_is_a_controlled_error(conn, world):
    early, _ = world
    llm = RoleRoutedLLM(
        {
            "SKEPTIC_PLAN": _plan(
                {"strategy": "ALTERNATIVE_STATE", "queries": ["streaming platform"]}
            ),
            "SKEPTIC_VERDICT": json.dumps({"objections": "not a list"}),
        }
    )
    with pytest.raises(AnalysisUnavailableError):
        _run(conn, llm, early)


def test_plan_prompt_offers_value_and_source_reliability_strategies():
    from app.reasoning import skeptic

    for strategy in ("CONFLICTING_VALUE", "SOURCE_RELIABILITY"):
        assert strategy in skeptic.PLAN_SYSTEM
    # A source's unreliability is usually found in a LATER check, so that
    # strategy must search for later evidence.
    assert "SOURCE_RELIABILITY" in skeptic._TEMPORAL_STRATEGIES
    assert "CONFLICTING_VALUE" not in skeptic._TEMPORAL_STRATEGIES


def _bundles(*strategies):
    from app.schemas.reasoning import CounterBundle, SkepticPlan

    return SkepticPlan(bundles=[CounterBundle(strategy=s, queries=["q"]) for s in strategies])


def _out(terms=("fresh waste",)):
    return PrimaryOutput.model_validate(
        {"answer_summary": "s", "status": "SUPPORTED", "claims": [], "search_terms": list(terms)}
    )


def test_a_reliability_question_always_gets_a_source_reliability_bundle():
    plan = skeptic.ensure_reliability_bundle(
        "Give the waste figures and say how reliable they are.",
        _out(),
        _bundles("DIRECT_CONTRADICTION", "ALTERNATIVE_STATE"),
    )
    strategies = [b.strategy for b in plan.bundles]
    assert strategies == ["DIRECT_CONTRADICTION", "SOURCE_RELIABILITY"]  # cap of 2 kept
    assert all("fresh waste" in q for q in plan.bundles[-1].queries)


def test_an_existing_reliability_bundle_or_an_unrelated_question_is_left_alone():
    planned = _bundles("CONFLICTING_VALUE", "SOURCE_RELIABILITY")
    assert skeptic.ensure_reliability_bundle("How reliable is it?", _out(), planned) is planned
    ordinary = _bundles("DIRECT_CONTRADICTION")
    assert skeptic.ensure_reliability_bundle("Who signed it?", _out(), ordinary) is ordinary
