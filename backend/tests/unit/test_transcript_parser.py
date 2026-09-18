from app.ingestion.parsers import transcript

TEAMS_HEADER = """Meeting: Solution demo & value workshop
Customer: Acme Org (Grocery Retail, EMEA)
Date: 2024-03-20
Phase: Pre-Sales
Attendees: Lena Fischer (Acme), Sofia Almeida (Acme), Marco Rossi (RELEX)

"""


def _units(conn, text: str, document_id: str = "doc1"):
    doc = transcript.parse(text, document_id, f"{document_id}.txt")
    return transcript.assign_locators_and_merge(conn, document_id, doc.fragments), doc


def test_merges_consecutive_fragments_from_same_speaker(conn):
    body = (
        "Marco Rossi\n1:201:20\nMR\n"
        "Marco Rossi 1 minute 20 seconds\n"
        "Good. So we will walk through forecasting first,\n"
        "Marco Rossi 1 minute 27 seconds\n"
        "then replenished,\n"
    )
    units, _ = _units(conn, TEAMS_HEADER + body)
    assert len(units) == 1
    unit = units[0]
    assert unit.speaker_sender == "Marco Rossi"
    assert unit.raw_text == "Good. So we will walk through forecasting first, then replenished,"
    assert unit.natural_locator == "t80"


def test_new_speaker_starts_a_new_unit(conn):
    body = (
        "Marco Rossi\n1:041:04\nMR\nMarco Rossi 1 minute 4 seconds\nThanks for the time today.\n"
        "Lena Fischer\n1:111:11\nLF\nLena Fischer 1 minute 11 seconds\nYes.\n"
    )
    units, _ = _units(conn, TEAMS_HEADER + body)
    assert [u.speaker_sender for u in units] == ["Marco Rossi", "Lena Fischer"]
    assert units[0].raw_text == "Thanks for the time today."
    assert units[1].raw_text == "Yes."


def test_unknown_speaker_is_its_own_anonymous_unit_not_merged_into_prior_speaker(conn):
    header = TEAMS_HEADER.replace(
        "Attendees: Lena Fischer (Acme), Sofia Almeida (Acme), Marco Rossi (RELEX)",
        "Attendees: Lena Fischer (Acme), Robert Kahn (Acme CFO)",
    )
    body = (
        "Lena Fischer\n0:240:24\nLF\nLena Fischer 24 seconds\nYeah.\n"
        "Unknown Speaker\n0:250:25\nUS\nUnknown Speaker 25 seconds\nYou're on mute.\n"
        "Robert Kahn\n0:280:28\nRK\nRobert Kahn 28 seconds\nSorry.\n"
    )
    units, _ = _units(conn, header + body)
    assert [u.speaker_sender for u in units] == ["Lena Fischer", "Unknown Speaker", "Robert Kahn"]
    assert units[0].raw_text == "Yeah."  # not merged with the next line
    assert units[1].raw_text == "You're on mute."


def test_speaker_name_mismatch_between_header_and_body_diacritics_still_matches(conn):
    # The corpus itself is inconsistent here: the Attendees header spells
    # a name with an o-with-stroke, but that speaker's own caption lines
    # render it with a plain "o". Losing these turns would misattribute
    # them to whoever spoke immediately before.
    header = TEAMS_HEADER.replace(
        "Attendees: Lena Fischer (Acme), Sofia Almeida (Acme), Marco Rossi (RELEX)",
        "Attendees: Marco Rossi (RELEX), Henrik Sørensen (RELEX)",
    )
    body = (
        "Henrik Sorensen\n8:598:59\nHS\n"
        "Henrik Sorensen 8 minutes 59 seconds\n"
        "case wording to Marco and that is the...\n"
    )
    units, _ = _units(conn, header + body)
    assert len(units) == 1
    # Stored under the canonical (header) spelling, not the body's.
    assert units[0].speaker_sender == "Henrik Sørensen"


def test_truncated_statement_ending_in_em_dash_is_flagged_and_preserved_verbatim(conn):
    body = (
        "Sofia Almeida\n7:117:11\nSA\n"
        "Sofia Almeida 7 minutes 11 seconds\n"
        "There are about four where it\n"
        "Sofia Almeida 7 minutes 16 seconds\n"
        "is bad. The obvious ones are —\n"
        "Lena Fischer\n7:217:21\nLF\n"
        "Lena Fischer 7 minutes 21 seconds\n"
        "Sorry, is that your screen or ours?\n"
    )
    units, _ = _units(conn, TEAMS_HEADER + body)
    sofia_unit = units[0]
    assert sofia_unit.raw_text == "There are about four where it is bad. The obvious ones are —"
    assert sofia_unit.is_truncated is True
    assert units[1].is_truncated is False


def test_internal_format_preserves_anonymous_speaker_labels_verbatim(conn):
    header = (
        "Meeting: Internal handover, pre-sales to delivery\n"
        "Customer: Acme Org (Grocery Retail, EMEA)\n"
        "Date: 2024-07-09\n"
        "Phase: Implementation\n"
        "Attendees: Marco Rossi (RELEX), Kwame Boateng (RELEX)\n\n"
    )
    body = (
        "Me: So this is handover. What is not in either of those?\n"
        "Them: A lot, honestly.\n"
        "Them: Kahn signed on the basis that this reduces fresh food waste.\n"
        "Me: Twelve months from signature.\n"
    )
    units, _ = _units(conn, header + body, "doc4")
    assert [u.speaker_sender for u in units] == ["Me", "Them", "Me"]
    # The two consecutive "Them:" lines merge into one turn.
    assert units[1].raw_text == (
        "A lot, honestly. Kahn signed on the basis that this reduces fresh food waste."
    )


def test_internal_format_never_assigns_a_roster_name_to_me_or_them(conn):
    header = (
        "Meeting: Internal call\nCustomer: Acme Org\nDate: 2024-07-09\nPhase: Implementation\n"
        "Attendees: Marco Rossi (RELEX), Kwame Boateng (RELEX)\n\n"
    )
    units, _ = _units(conn, header + "Me: Kwame told me the extraction succeeded.\n", "doc4")
    assert units[0].speaker_sender == "Me"
    assert units[0].speaker_sender not in {"Marco Rossi", "Kwame Boateng"}


def test_deleting_a_turn_does_not_fuse_its_now_adjacent_same_speaker_neighbors(conn):
    """The corpus-critical case: a two-party dialogue where Me/Them
    strictly alternate. If a middle turn is deleted, its two neighbors
    become file-adjacent and share a speaker, but they were never one
    continuous utterance -- there was a real, different-speaker turn
    between them. Naive same-speaker merging would fabricate a turn that
    never happened; genesis-position gap detection must prevent it.
    """
    header = (
        "Meeting: Internal call\nCustomer: Acme Org\nDate: 2024-07-09\nPhase: Implementation\n"
        "Attendees: Marco Rossi (RELEX), Kwame Boateng (RELEX)\n\n"
    )
    original = header + "Me: First turn.\nThem: Second turn.\nMe: Third turn.\nThem: Fourth turn.\n"
    units_before, doc_before = _units(conn, original, "doc-gap")
    assert [u.raw_text for u in units_before] == [
        "First turn.",
        "Second turn.",
        "Third turn.",
        "Fourth turn.",
    ]
    first_locator = units_before[0].natural_locator
    third_locator = units_before[2].natural_locator

    # Simulate physically scrubbing "Second turn." from the source file,
    # the way Phase 5's purge would.
    after_delete = header + "Me: First turn.\nMe: Third turn.\nThem: Fourth turn.\n"
    units_after, _ = _units(conn, after_delete, "doc-gap")

    texts_after = [u.raw_text for u in units_after]
    assert "First turn." in texts_after
    assert "Third turn." in texts_after
    assert "First turn. Third turn." not in texts_after  # must not have been fused

    by_text = {u.raw_text: u for u in units_after}
    assert by_text["First turn."].natural_locator == first_locator
    assert by_text["Third turn."].natural_locator == third_locator
