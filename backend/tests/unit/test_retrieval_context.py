from app.retrieval import context


def test_email_unit_gets_plus_minus_one(conn, seed_units):
    ids = seed_units(
        conn,
        "mail",
        [
            f"This is a full length email message number {i} with plenty of words in it."
            for i in range(6)
        ],
        document_type="EMAIL",
    )
    (window,) = context.expand(conn, [ids[3]])
    assert window.unit_ids == (ids[2], ids[3], ids[4])
    assert window.context_ids == (ids[2], ids[4])
    assert window.anchor_id == ids[3]


def test_short_transcript_turn_expands_past_plus_minus_one(conn, seed_units):
    long = "We reviewed the whole ordering parameter set at length this morning together."
    ids = seed_units(
        conn,
        "meeting",
        [
            long,
            long,
            "Should we move the go-live date to December then?",
            "Yes.",
            "Sounds good.",
            long,
            long,
        ],
    )
    (window,) = context.expand(conn, [ids[3]])
    # "Yes." alone must not be shown without the question it answers.
    assert ids[2] in window.unit_ids
    assert ids[4] in window.unit_ids
    assert len(window.unit_ids) > 3


def test_window_is_bounded(conn, seed_units):
    ids = seed_units(conn, "meeting", ["Yes."] * 20)
    (window,) = context.expand(conn, [ids[10]])
    assert len(window.unit_ids) <= 2 * context.MAX_RADIUS + 1


def test_window_never_crosses_documents_or_edges(conn, seed_units):
    a = seed_units(conn, "a", ["Yes.", "Okay."])
    seed_units(conn, "b", ["Other document turn here."])
    (window,) = context.expand(conn, [a[0]])
    assert window.unit_ids[0] == a[0]
    assert all(i.startswith("EV-a-") for i in window.unit_ids)


def test_unknown_and_duplicate_anchors(conn, seed_units):
    ids = seed_units(conn, "doc", ["one two three four five six seven eight nine ten"])
    windows = context.expand(conn, [ids[0], ids[0], "EV-missing"])
    assert [w.anchor_id for w in windows] == [ids[0]]


def test_context_dependence_heuristic():
    assert context.is_context_dependent("Yes.")
    assert context.is_context_dependent("Sounds good, let us go ahead with that plan as written.")
    assert not context.is_context_dependent(
        "The extract we received contains a column nobody asked for and it identifies people."
    )
