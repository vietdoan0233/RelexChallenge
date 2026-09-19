import json

import pytest

from app.core.enums import CaseStatus, Confidence, Stance
from app.schemas.reasoning import PrimaryOutput
from app.validation import receipt_validator as v


def _output(**overrides):
    base = {
        "answer_summary": "Bakery moved to its own workstream.",
        "status": "SUPPORTED",
        "claims": [],
    }
    base.update(overrides)
    return PrimaryOutput.model_validate(base)


def _claim(support, *, stance="AGREEMENT", confidence="HIGH", conflicts=(), text="A claim."):
    return {
        "claim_text": text,
        "stance": stance,
        "confidence": confidence,
        "supporting_evidence_ids": list(support),
        "conflicting_evidence_ids": list(conflicts),
    }


@pytest.fixture
def corpus(conn, seed_units):
    return seed_units(
        conn,
        "meeting",
        [
            ("Shall bakery stay in the fresh workstream?", "Ana Duarte", "2025-01-10"),
            ("Yes.", "Lena Fischer", "2025-01-10"),
            ("Bakery is its own workstream now.", "Marco Rossi", "2025-06-10"),
        ],
    )


def test_fabricated_evidence_id_is_rejected_and_claim_dropped(conn, corpus):
    out = _output(claims=[_claim(["EV-invented-99"])])
    receipt = v.validate_primary(conn, out, query="q", visible_ids=None)
    assert receipt.claims == []
    assert receipt.validation.rejected_evidence_ids == ["EV-invented-99"]
    assert receipt.validation.dropped_claims == 1
    assert receipt.status == CaseStatus.INSUFFICIENT_EVIDENCE
    # The model's own summary is not shown when nothing supports it.
    assert receipt.answer_summary == v.NO_SUPPORT_SUMMARY


def test_real_id_outside_the_visible_set_is_rejected(conn, corpus):
    out = _output(claims=[_claim([corpus[2]])])
    receipt = v.validate_primary(conn, out, query="q", visible_ids={corpus[0]})
    assert receipt.claims == []
    assert receipt.validation.rejected_evidence_ids == [corpus[2]]


def test_mixed_valid_and_fake_ids_keep_only_the_valid(conn, corpus):
    out = _output(claims=[_claim([corpus[2], "EV-fake"])])
    receipt = v.validate_primary(conn, out, query="q", visible_ids=None)
    assert receipt.claims[0].supporting_evidence_ids == [corpus[2]]
    assert receipt.validation.rejected_evidence_ids == ["EV-fake"]
    assert receipt.status == CaseStatus.SUPPORTED


def test_dropping_some_claims_lowers_status_from_supported(conn, corpus):
    out = _output(claims=[_claim([corpus[2]]), _claim(["EV-fake"])])
    receipt = v.validate_primary(conn, out, query="q", visible_ids=None)
    assert len(receipt.claims) == 1
    assert receipt.status == CaseStatus.PARTIALLY_SUPPORTED


def test_uncertain_claim_may_stand_without_support(conn, corpus):
    out = _output(claims=[_claim([], stance="UNCERTAIN", confidence="LOW")])
    receipt = v.validate_primary(conn, out, query="q", visible_ids=None)
    assert len(receipt.claims) == 1
    # ...but a receipt with no supported claim at all is still insufficient.
    assert receipt.status == CaseStatus.INSUFFICIENT_EVIDENCE


def test_model_cannot_supply_speaker_date_or_quote(conn, corpus):
    out = PrimaryOutput.model_validate_json(
        json.dumps(
            {
                "answer_summary": "x",
                "status": "SUPPORTED",
                "claims": [
                    {
                        "claim_text": "c",
                        "stance": "AGREEMENT",
                        "confidence": "HIGH",
                        "supporting_evidence_ids": [corpus[2]],
                        "speaker": "Invented Person",
                        "date": "1999-01-01",
                        "quote": "invented quote",
                        "document": "invented.txt",
                    }
                ],
            }
        )
    )
    validated = v.validate_primary(conn, out, query="q", visible_ids=None)
    receipt = v.hydrate_receipt(conn, validated, case_id="c1", created_at="t")
    cite = receipt.claims[0].support[0]
    assert cite.speaker_sender == "Marco Rossi"
    assert cite.event_date == "2025-06-10"
    assert cite.raw_text == "Bakery is its own workstream now."
    assert cite.document_id == "meeting"
    dumped = receipt.model_dump_json()
    assert "Invented Person" not in dumped and "invented quote" not in dumped


def test_truncated_only_support_caps_confidence(conn, seed_units):
    ids = seed_units(conn, "d", ["Shelf life is populated on"])
    conn.execute("UPDATE evidence_units SET is_truncated = 1")
    receipt = v.validate_primary(conn, _output(claims=[_claim(ids)]), query="q", visible_ids=None)
    assert receipt.claims[0].confidence == Confidence.LOW
    assert receipt.validation.downgraded_claims == 1


def test_timeline_is_dropped_without_evidence_and_sorted_chronologically(conn, corpus):
    out = _output(
        claims=[_claim([corpus[2]])],
        timeline_events=[
            {
                "event_text": "later",
                "state": "SUPERSEDED",
                "confidence": "HIGH",
                "evidence_ids": [corpus[2]],
            },
            {
                "event_text": "ungrounded",
                "state": "AGREEMENT",
                "confidence": "HIGH",
                "evidence_ids": ["EV-fake"],
            },
            {
                "event_text": "earlier",
                "state": "PROPOSAL",
                "confidence": "MEDIUM",
                "evidence_ids": [corpus[0]],
            },
        ],
    )
    receipt = v.validate_primary(conn, out, query="q", visible_ids=None)
    assert [e.event_text for e in receipt.timeline_events] == ["earlier", "later"]
    assert receipt.validation.dropped_timeline_events == 1
    served = v.hydrate_receipt(conn, receipt, case_id="c", created_at="t")
    assert [e.event_date for e in served.timeline_events] == ["2025-01-10", "2025-06-10"]
    assert served.timeline_events[0].state == Stance.PROPOSAL


def test_deleted_evidence_cannot_render_from_a_stored_case(conn, corpus):
    out = _output(claims=[_claim([corpus[2]])])
    validated = v.validate_primary(conn, out, query="q", visible_ids=None)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM evidence_units WHERE evidence_id = ?", (corpus[2],))
    served = v.hydrate_receipt(conn, validated, case_id="c", created_at="t")
    assert served.claims == []
    assert served.status == CaseStatus.INSUFFICIENT_EVIDENCE
    assert "Bakery is its own workstream" not in served.model_dump_json()


def test_evidence_view_returns_neighbour_context_from_the_database(conn, corpus):
    view = v.evidence_view(conn, corpus[1])
    assert view.citation.raw_text == "Yes."
    assert [c.evidence_id for c in view.context_before] == [corpus[0]]
    assert [c.evidence_id for c in view.context_after] == [corpus[2]]
    assert v.evidence_view(conn, "EV-missing") is None


def test_evidence_ids_are_stripped_from_prose_fields(conn, corpus):
    out = _output(
        answer_summary=f"Bakery moved [{corpus[2]}] to its own track ({corpus[0]}).",
        claims=[_claim([corpus[2]], text=f"It became separate [{corpus[2]}].")],
        missing_information=[f"Nothing on cost in {corpus[1]}."],
    )
    receipt = v.validate_primary(conn, out, query="q", visible_ids=None)
    assert "EV-" not in receipt.answer_summary
    assert receipt.answer_summary == "Bakery moved to its own track ()."
    assert receipt.claims[0].claim_text == "It became separate."
    assert "EV-" not in receipt.missing_information[0]
    # The id fields, not the prose, carry provenance.
    assert receipt.claims[0].supporting_evidence_ids == [corpus[2]]


def test_prose_that_is_only_an_evidence_id_never_falls_back_to_the_raw_id(conn, corpus):
    out = _output(
        answer_summary=f"[{corpus[2]}]",
        claims=[
            _claim([corpus[2]], text=f"[{corpus[2]}]"),
            _claim([corpus[2]], text="A real statement."),
        ],
        timeline_events=[
            {
                "event_text": f"[{corpus[0]}]",
                "state": "PROPOSAL",
                "confidence": "LOW",
                "evidence_ids": [corpus[0]],
            },
        ],
        missing_information=[f"[{corpus[1]}]", "Cost is not stated."],
        related_questions=[f"{corpus[0]}"],
        conflict_resolution=f"[{corpus[1]}]",
    )
    receipt = v.validate_primary(conn, out, query="q", visible_ids=None)
    prose = [
        receipt.answer_summary,
        receipt.conflict_resolution or "",
        *[c.claim_text for c in receipt.claims],
        *receipt.missing_information,
        *receipt.related_questions,
    ]
    assert not any("EV-" in text for text in prose)
    assert [c.claim_text for c in receipt.claims] == ["A real statement."]
    assert receipt.validation.dropped_claims == 1
    assert receipt.timeline_events == []
    assert receipt.missing_information == ["Cost is not stated."]
    assert receipt.related_questions == []
    assert receipt.answer_summary == v.EMPTY_SUMMARY
    assert not receipt.conflict_resolution
