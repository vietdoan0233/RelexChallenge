from app.ingestion.parsers import email

DISCLAIMER = "*** SYNTHETIC DATA. Entirely fictional.\n\n"


def test_splits_reverse_chronological_thread_into_one_unit_per_message():
    text = DISCLAIMER + (
        "Subject: Shelf life field mapping\n"
        "From: Nadia Haddad <n.haddad@relexsolutions.example>\n"
        "Date: Thursday, October 30, 2025 12:02 PM\n"
        "To: Ana Duarte <ana.duarte@relexsolutions.example>\n"
        "Cc: Priya Nair <priya.nair@acme-org.example>\n"
        "Messages in thread: 2\n\n"
        "We proceeded. Nobody objected.\n\n"
        "Nadia Haddad\n"
        "Solution Consultant\n\n\n"
        "From: Ana Duarte <ana.duarte@relexsolutions.example>\n"
        "Sent: Thursday, September 4, 2025 14:20\n"
        "To: Nadia Haddad <n.haddad@relexsolutions.example>\n"
        "Subject: Re: Shelf life field mapping\n\n"
        "Following up on the below.\n"
    )
    doc = email.parse(text, "doc1", "doc1.txt")
    assert len(doc.units) == 2
    assert doc.units[0].speaker_sender == "Nadia Haddad"
    assert doc.units[0].speaker_email == "n.haddad@relexsolutions.example"
    assert "We proceeded. Nobody objected." in doc.units[0].raw_text
    assert doc.units[1].speaker_sender == "Ana Duarte"
    # Each message keeps its own date -- the thread is reverse
    # chronological, so the older, second message must not inherit the
    # newer first message's date.
    assert doc.units[0].event_date == "2025-10-30"
    assert doc.units[1].event_date == "2025-09-04"


def test_german_locale_headers_are_recognized_as_a_message_boundary():
    # A real corpus bug: German-headed messages (Von/Gesendet/An/Betreff)
    # were previously invisible to the English-only "From:" boundary
    # check and silently merged into the body of the preceding message.
    text = DISCLAIMER + (
        "Subject: Chain wide rollout\n"
        "From: Robert Kahn <robert.kahn@acme-org.example>\n"
        "Date: Monday, June 29, 2026 10:22 AM\n"
        "To: Lena Fischer <lena.fischer@acme-org.example>\n"
        "Messages in thread: 2\n\n"
        "Then I will ask him.\n\n"
        "Von: Lena Fischer <lena.fischer@acme-org.example>\n"
        "Gesendet: Montag, 29. Juni 2026 10:15\n"
        "An: Robert Kahn <robert.kahn@acme-org.example>\n"
        "Betreff: Re: Chain wide rollout\n\n"
        "It sits under logistics IT.\n"
    )
    doc = email.parse(text, "doc20", "doc20.txt")
    assert len(doc.units) == 2
    assert doc.units[1].speaker_sender == "Lena Fischer"
    assert doc.units[1].raw_text == "It sits under logistics IT."
    assert doc.units[1].event_date == "2026-06-29"


def test_swedish_locale_headers_and_den_date_format_are_recognized():
    text = DISCLAIMER + (
        "Subject: DC-2 feed failures\n"
        "From: Priya Nair <priya.nair@acme-org.example>\n"
        "Date: Friday, March 14, 2025 11:05\n"
        "To: Tomas Lindholm <tomas.lindholm@relexsolutions.example>\n"
        "Messages in thread: 2\n\n"
        "Escalating this.\n\n"
        "Från: Tomas Lindholm <tomas.lindholm@relexsolutions.example>\n"
        "Skickat: den 17 mars 2025 14:15\n"
        "Till: Priya Nair <priya.nair@acme-org.example>\n"
        "Ämne: Re: DC-2 feed failures\n\n"
        "Looking into it now.\n"
    )
    doc = email.parse(text, "doc16", "doc16.txt")
    assert len(doc.units) == 2
    assert doc.units[1].speaker_sender == "Tomas Lindholm"
    assert doc.units[1].event_date == "2025-03-17"


def test_redacted_sender_header_remains_a_separate_parseable_message():
    text = DISCLAIMER + (
        "Subject: Shelf life field mapping\n"
        "From: Nadia Haddad <n.haddad@relexsolutions.example>\n"
        "Date: Thursday, October 30, 2025 12:02 PM\n"
        "To: Ana Duarte <ana.duarte@relexsolutions.example>\n"
        "Messages in thread: 2\n\n"
        "We proceeded. Nobody objected.\n\n"
        "From: [REDACTED SENDER]\n"
        "Sent: Thursday, September 4, 2025 14:20\n"
        "To: Nadia Haddad <n.haddad@relexsolutions.example>\n"
        "Subject: Re: Shelf life field mapping\n\n"
        "Following up on the below.\n"
    )
    doc = email.parse(text, "doc-redacted", "doc-redacted.txt")
    assert len(doc.units) == 2
    # The two messages stay separate -- the redacted header does not
    # cause it to merge into the preceding message's body.
    assert doc.units[0].raw_text == "We proceeded. Nobody objected."
    assert doc.units[1].speaker_sender == "[REDACTED SENDER]"
    assert doc.units[1].raw_text == "Following up on the below."
    # No fabricated email address for the anonymized sender.
    assert doc.units[1].speaker_email is None


def test_empty_message_body_is_skipped_not_emitted_as_a_blank_unit():
    text = DISCLAIMER + (
        "Subject: Empty reply\n"
        "From: Ana Duarte <ana.duarte@relexsolutions.example>\n"
        "Date: Thursday, October 30, 2025 12:02 PM\n"
        "To: Nadia Haddad <n.haddad@relexsolutions.example>\n"
        "Messages in thread: 1\n\n"
    )
    doc = email.parse(text, "doc-empty", "doc-empty.txt")
    assert doc.units == []


def test_no_from_header_produces_a_warning_not_a_crash():
    doc = email.parse(
        DISCLAIMER + "Just some stray text with no headers at all.\n", "doc-bad", "doc-bad.txt"
    )
    assert doc.units == []
    assert doc.warnings
