from app.retrieval.fusion import RRF_K, reciprocal_rank_fusion
from app.retrieval.lexical import Hit


def _hits(*ids):
    return [Hit(evidence_id=i, rank=r, score=0.0) for r, i in enumerate(ids, start=1)]


def test_item_in_both_lists_beats_item_in_one():
    fused = reciprocal_rank_fusion({"lexical": _hits("a", "b"), "semantic": _hits("b", "c")})
    assert [f.evidence_id for f in fused] == ["b", "a", "c"]
    assert fused[0].score == 1 / (RRF_K + 2) + 1 / (RRF_K + 1)
    assert fused[0].sources == {"lexical": 2, "semantic": 1}


def test_ties_break_by_evidence_id_deterministically():
    fused = reciprocal_rank_fusion({"lexical": _hits("b"), "semantic": _hits("a")})
    assert [f.evidence_id for f in fused] == ["a", "b"]


def test_limit_and_ranks_are_contiguous():
    fused = reciprocal_rank_fusion({"lexical": _hits("a", "b", "c")}, limit=2)
    assert [(f.evidence_id, f.rank) for f in fused] == [("a", 1), ("b", 2)]


def test_empty_input_gives_empty_output():
    assert reciprocal_rank_fusion({}) == []
    assert reciprocal_rank_fusion({"lexical": []}) == []
