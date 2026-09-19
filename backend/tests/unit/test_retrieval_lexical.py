from app.retrieval import lexical


def test_bm25_puts_the_stronger_match_first(conn, seed_units):
    ids = seed_units(
        conn,
        "doc",
        [
            "The weather was fine.",
            "Shelf life data is missing for bakery.",
            "Shelf life shelf life.",
        ],
    )
    hits = lexical.search(conn, "shelf life")
    assert [h.evidence_id for h in hits][0] == ids[2]
    assert [h.rank for h in hits] == [1, 2]
    assert ids[0] not in [h.evidence_id for h in hits]


def test_stemming_lets_agreed_find_agreement(conn, seed_units):
    ids = seed_units(conn, "doc", ["We reached agreement on the rollout.", "Lunch is at noon."])
    assert [h.evidence_id for h in lexical.search(conn, "Was it agreed?")] == [ids[0]]


def test_thread_title_rescues_a_short_unit(conn, seed_units):
    ids = seed_units(
        conn,
        "email",
        ["Received, thank you."],
        title="DC-2 incident log",
        document_type="EMAIL",
    )
    seed_units(conn, "other", ["Nothing relevant here."], title="Lunch plans")
    assert [h.evidence_id for h in lexical.search(conn, "incident log")] == [ids[0]]


def test_speaker_is_searchable(conn, seed_units):
    ids = seed_units(conn, "doc", [("We should wait.", "Priya Nair"), ("We should go.", "Marco")])
    assert [h.evidence_id for h in lexical.search(conn, "Priya")] == [ids[0]]


def test_after_date_keeps_only_strictly_later_units(conn, seed_units):
    ids = seed_units(
        conn,
        "doc",
        [
            ("bakery scope", "A", "2025-01-01"),
            ("bakery scope", "B", "2025-06-01"),
        ],
    )
    hits = lexical.search(conn, "bakery", after_date="2025-01-01")
    assert [h.evidence_id for h in hits] == [ids[1]]


def test_deleted_unit_cannot_be_returned_from_a_stale_fts_row(conn, seed_units):
    ids = seed_units(conn, "doc", ["bakery scope", "bakery timing"])
    # Delete the unit but leave its FTS row behind, as a partial purge might.
    conn.execute("DELETE FROM evidence_units WHERE evidence_id = ?", (ids[0],))
    assert [h.evidence_id for h in lexical.search(conn, "bakery")] == [ids[1]]


def test_hostile_query_text_never_raises(conn, seed_units):
    seed_units(conn, "doc", ["plain text"])
    for query in ['NEAR("a" b)', '"unbalanced', "a AND OR NOT", "***", "-:()", ""]:
        assert isinstance(lexical.search(conn, query), list)


def test_limit_is_respected(conn, seed_units):
    seed_units(conn, "doc", [f"bakery {i}" for i in range(20)])
    assert len(lexical.search(conn, "bakery", limit=5)) == 5
