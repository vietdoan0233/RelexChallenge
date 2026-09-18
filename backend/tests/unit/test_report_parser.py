from app.ingestion.parsers import report

DISCLAIMER = "*** SYNTHETIC DATA. Entirely fictional.\n\n"


def test_multi_bullet_section_splits_into_one_unit_per_bullet():
    text = DISCLAIMER + (
        "Subject: Weekly Acme update\n"
        "From: Ana Duarte <ana.duarte@relexsolutions.example>\n"
        "Date: Monday, April 6, 2026 17:30\n"
        "To: Lena Fischer <lena.fischer@acme-org.example>\n"
        "Messages in thread: 1\n\n"
        "Hi All,\n\n"
        "Topics worked on last week\n"
        "1.                  Q1 results compiled\n"
        "2.                  Bakery build continues\n"
        "3.                  Nightly article extract completed, no errors\n"
    )
    doc = report.parse(text, "doc1", "doc1.txt")
    bullets = [
        u.raw_text for u in doc.units if u.thread_context and "Topics worked" in u.thread_context
    ]
    assert bullets == [
        "Q1 results compiled",
        "Bakery build continues",
        "Nightly article extract completed, no errors",
    ]
    # A whole-section bundle would defeat the point of whole-unit
    # deletion: removing one person's bullet must not also erase the
    # other two, unrelated bullets.
    assert len(set(bullets)) == 3


def test_bullet_does_not_carry_the_section_label_in_raw_text():
    text = DISCLAIMER + (
        "Subject: Weekly update\nFrom: Ana Duarte <ana.duarte@relexsolutions.example>\n"
        "Date: Monday, April 6, 2026 17:30\nTo: Lena Fischer <lena.fischer@acme-org.example>\n"
        "Messages in thread: 1\n\n"
        "Topics planned for this week\n"
        "1.                Present Q1 results\n"
        "1.                Bakery build continues\n"
    )
    doc = report.parse(text, "doc1", "doc1.txt")
    # raw_text must stay byte-for-byte quotable; the section label lives
    # in thread_context instead, not spliced into the citation text.
    assert all("Topics planned" not in u.raw_text for u in doc.units)
    assert all("Topics planned for this week" in (u.thread_context or "") for u in doc.units)


def test_single_line_section_is_kept_as_one_unit():
    text = DISCLAIMER + (
        "Subject: Weekly update\nFrom: Ana Duarte <ana.duarte@relexsolutions.example>\n"
        "Date: Monday, April 6, 2026 17:30\nTo: Lena Fischer <lena.fischer@acme-org.example>\n"
        "Messages in thread: 1\n\n"
        "Timeline\nOn plan.\n"
    )
    doc = report.parse(text, "doc1", "doc1.txt")
    timeline_units = [u for u in doc.units if u.thread_context and "Timeline" in u.thread_context]
    assert len(timeline_units) == 1
    assert timeline_units[0].raw_text == "On plan."


def test_free_paragraph_before_any_section_header_becomes_its_own_unit():
    text = DISCLAIMER + (
        "Subject: Weekly update\nFrom: Ana Duarte <ana.duarte@relexsolutions.example>\n"
        "Date: Monday, April 6, 2026 17:30\nTo: Lena Fischer <lena.fischer@acme-org.example>\n"
        "Messages in thread: 1\n\n"
        "Q1 fresh waste 3.4% against a 4.1% baseline.\n\n"
        "Timeline\nOn plan.\n"
    )
    doc = report.parse(text, "doc1", "doc1.txt")
    assert doc.units[0].raw_text == "Q1 fresh waste 3.4% against a 4.1% baseline."
    assert doc.units[0].thread_context == "Weekly update"
