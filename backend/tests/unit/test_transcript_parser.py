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


def test_redacted_speaker_marker_opens_a_normal_fragment_and_content_survives(conn):
    header = TEAMS_HEADER.replace(
        "Attendees: Lena Fischer (Acme), Sofia Almeida (Acme), Marco Rossi (RELEX)",
        "Attendees: Lena Fischer (Acme), Marco Rossi (RELEX)",
    )
    body = (
        "Lena Fischer\n0:240:24\nLF\nLena Fischer 24 seconds\nYeah.\n"
        "[REDACTED SPEAKER]\n0:250:25\n"
        "[REDACTED SPEAKER] 5 seconds\nWe discussed the budget privately.\n"
        "Marco Rossi\n0:280:28\nMR\nMarco Rossi 28 seconds\nSorry, go ahead.\n"
    )
    units, _ = _units(conn, header + body)
    assert [u.speaker_sender for u in units] == [
        "Lena Fischer",
        "[REDACTED SPEAKER]",
        "Marco Rossi",
    ]
    # The redacted turn's body survives ingestion, not silently dropped
    # as untraceable chrome or merged into a neighboring turn.
    assert units[1].raw_text == "We discussed the budget privately."
    # Neighboring named turns still parse and stay separate.
    assert units[0].raw_text == "Yeah."
    assert units[2].raw_text == "Sorry, go ahead."


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


# ------------------------------------------------ dial-in (phone-number) speaker

_PHONE = "+358 40 5512 097"

# Mirrors the real export shape: the dial-in is not in the Attendees
# header, and its chrome is number / doubled timestamp / "+4" chip / marker.
_DIAL_IN_BODY = (
    "Lena Fischer\n6:346:34\nLF\n"
    "Lena Fischer 6 minutes 34 seconds\n"
    "Ninety-nine on everything, in theory, which is\n"
    f"{_PHONE}\n6:406:40\n+4\n"
    f"{_PHONE} 6 minutes 40 seconds\n"
    "Mm-hm.\n"
    "Lena Fischer\n6:446:44\nLF\n"
    "Lena Fischer 6 minutes 44 seconds\n"
    "why we carry so much stock.\n"
    "Marco Rossi\n6:486:48\nMR\n"
    "Marco Rossi 6 minutes 48 seconds\n"
    "Okay, yeah.\n"
)


def test_phone_number_speaker_becomes_its_own_unit_with_no_chrome_leak(conn):
    units, doc = _units(conn, TEAMS_HEADER + _DIAL_IN_BODY)

    assert [(u.speaker_sender, u.raw_text) for u in units] == [
        ("Lena Fischer", "Ninety-nine on everything, in theory, which is"),
        (_PHONE, "Mm-hm."),
        ("Lena Fischer", "why we carry so much stock."),
        ("Marco Rossi", "Okay, yeah."),
    ]
    for unit in units:
        assert "+358" not in unit.raw_text
        assert "+4" not in unit.raw_text
        assert "minutes" not in unit.raw_text
    # Timestamp text and natural locator come from the marker line, as for
    # any named speaker.
    assert units[1].timestamp_text == "6 minutes 40 seconds"
    assert units[1].natural_locator == "t400"
    # A caller who is not in the Attendees header is not added to it.
    assert _PHONE not in doc.attendees


def test_dial_in_interjection_does_not_fuse_the_interrupted_speakers_turn(conn):
    # The pre-fix behaviour merged both Lena fragments (and the dial-in's
    # chrome and reply) into one unit. The interjection is a real turn
    # between them, so they must stay separate.
    units, _ = _units(conn, TEAMS_HEADER + _DIAL_IN_BODY)
    lena_texts = [u.raw_text for u in units if u.speaker_sender == "Lena Fischer"]
    assert lena_texts == [
        "Ninety-nine on everything, in theory, which is",
        "why we carry so much stock.",
    ]


def test_consecutive_fragments_from_the_same_dial_in_merge_into_one_turn(conn):
    body = (
        f"{_PHONE}\n1:101:10\n+4\n{_PHONE} 1 minute 10 seconds\nYes, I can hear\n"
        f"{_PHONE} 1 minute 14 seconds\nyou fine.\n"
        "Marco Rossi\n1:201:20\nMR\nMarco Rossi 1 minute 20 seconds\nGood.\n"
    )
    units, _ = _units(conn, TEAMS_HEADER + body)
    assert [(u.speaker_sender, u.raw_text) for u in units] == [
        (_PHONE, "Yes, I can hear you fine."),
        ("Marco Rossi", "Good."),
    ]
    assert units[0].timestamp_text == "1 minute 10 seconds"


def test_phone_marker_with_seconds_only_duration_splits_number_from_duration(conn):
    # "+1 555 010 0199 45 seconds": the duration digits must not be
    # absorbed into the number.
    body = "+1 555 010 0199\n0:450:45\n+1\n+1 555 010 0199 45 seconds\nHello?\n"
    units, _ = _units(conn, TEAMS_HEADER + body)
    assert [(u.speaker_sender, u.raw_text, u.timestamp_text) for u in units] == [
        ("+1 555 010 0199", "Hello?", "45 seconds")
    ]


def test_phone_number_inside_caption_text_is_not_treated_as_chrome(conn):
    # Position, not shape, decides chrome: a phone-shaped or "+4"-shaped
    # caption line that is not followed by / preceded by the timestamp
    # chrome stays in the turn it belongs to. Meaning is never repaired.
    body = (
        "Marco Rossi\n2:002:00\nMR\nMarco Rossi 2 minutes\n"
        "Call the supplier on\n"
        "+358 40 5512 097\n"
        "and ask about the delta,\n"
        "+4\n"
        "and no more.\n"
    )
    units, _ = _units(conn, TEAMS_HEADER + body)
    assert len(units) == 1
    assert units[0].raw_text == (
        "Call the supplier on +358 40 5512 097 and ask about the delta, +4 and no more."
    )


def test_truncated_dial_in_statement_is_flagged_and_not_completed(conn):
    body = f"{_PHONE}\n3:003:00\n+4\n{_PHONE} 3 minutes\nThe number I have is 4\n"
    units, _ = _units(conn, TEAMS_HEADER + body)
    assert len(units) == 1
    assert units[0].speaker_sender == _PHONE
    assert units[0].raw_text == "The number I have is 4"


# --------------------------------------------- unlisted "Guest N" participants

# Mirrors the real export shape: "Guest 1" is not in the Attendees header;
# its chrome is label / doubled timestamp / "G1" chip / marker.
_GUEST_BODY = (
    "Lena Fischer\n3:543:54\nLF\nLena Fischer 3 minutes 54 seconds\nYeah, yeah.\n"
    "Guest 1\n3:573:57\nG1\nGuest 1 3 minutes 57 seconds\n"
    "done half of the ownership,\n"
    "Marco Rossi\n4:044:04\nMR\nMarco Rossi 4 minutes 4 seconds\nRight.\n"
)


def test_guest_speaker_becomes_its_own_unit_with_no_chrome_leak(conn):
    units, doc = _units(conn, TEAMS_HEADER + _GUEST_BODY)

    assert [(u.speaker_sender, u.raw_text) for u in units] == [
        ("Lena Fischer", "Yeah, yeah."),
        ("Guest 1", "done half of the ownership,"),
        ("Marco Rossi", "Right."),
    ]
    assert units[1].timestamp_text == "3 minutes 57 seconds"
    assert units[1].natural_locator == "t237"
    assert "Guest 1" not in doc.attendees
    for unit in units:
        assert "G1" not in unit.raw_text
        assert "3:57" not in unit.raw_text


def test_guest_label_or_chip_inside_caption_text_is_not_treated_as_chrome(conn):
    body = (
        "Marco Rossi\n2:002:00\nMR\nMarco Rossi 2 minutes\n"
        "We asked\n"
        "Guest 1\n"
        "to join and the room code was\n"
        "G1\n"
        "on the invite.\n"
    )
    units, _ = _units(conn, TEAMS_HEADER + body)
    assert len(units) == 1
    assert units[0].raw_text == ("We asked Guest 1 to join and the room code was G1 on the invite.")
