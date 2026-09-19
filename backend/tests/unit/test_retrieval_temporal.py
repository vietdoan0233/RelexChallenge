from app.retrieval import temporal


def test_earliest_date(conn, seed_units):
    ids = seed_units(conn, "doc", [("a", "S", "2025-03-01"), ("b", "S", "2025-01-01")])
    assert temporal.earliest_date(conn, ids) == "2025-01-01"
    assert temporal.earliest_date(conn, []) is None


def test_sweep_returns_only_strictly_later_evidence(conn, seed_units):
    ids = seed_units(
        conn,
        "doc",
        [
            ("bakery is out of scope", "A", "2025-01-01"),
            ("bakery is now its own workstream", "B", "2025-06-01"),
            ("bakery timeline slips", "C", "2025-09-01"),
        ],
    )
    sweep = temporal.later_evidence_sweep(
        conn, terms=["bakery"], after_date="2025-01-01", already_seen={ids[1]}
    )
    assert {h.evidence_id for h in sweep.hits} == {ids[1], ids[2]}
    # ids[1] was already surfaced, so only ids[2] is new.
    assert sweep.new_evidence_ids == [ids[2]]
    assert sweep.after_date == "2025-01-01"


def test_sweep_with_no_later_evidence_is_empty(conn, seed_units):
    seed_units(conn, "doc", [("bakery scope", "A", "2025-01-01")])
    sweep = temporal.later_evidence_sweep(
        conn, terms=["bakery"], after_date="2025-01-01", already_seen=set()
    )
    assert sweep.hits == []
    assert sweep.new_evidence_ids == []
