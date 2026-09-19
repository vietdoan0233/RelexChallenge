import re

import pytest

from app.retrieval import text


def test_topic_terms_drop_scaffolding_and_duplicates():
    terms = text.topic_terms("What did the master data assessment report as complete? Data data.")
    assert terms == ["master", "data", "assessment", "report", "complete"]


def test_temporal_cue_words_are_not_topic_terms():
    assert "current" not in text.topic_terms("What is the current shelf life status?")


@pytest.mark.parametrize(
    "query",
    [
        "What is the current plan?",
        "Is it still in scope?",
        "How did this change over time?",
        "Was the decision superseded?",
        "Who is responsible now?",
    ],
)
def test_temporal_queries_are_detected(query):
    assert text.is_temporal_query(query)


def test_plain_lookup_is_not_temporal():
    assert not text.is_temporal_query("Who attended the kickoff meeting?")


def test_light_stem_bridges_common_suffixes():
    assert text.light_stem("agreed") == "agre"
    assert text.light_stem("populated") == "populat"
    # Doubled consonant from inflection is undone: committed -> commit.
    assert text.light_stem("committed") == "commit"
    assert text.light_stem("occurred") == "occur"
    # Too short to stem safely.
    assert text.light_stem("used") == "used"


def test_irregular_derivations_are_expanded():
    assert text.term_variants("decided") == ["decid", "decis"]


def test_match_expression_quotes_every_term():
    expr = text.fts_match_expression(["agreed", "id"])
    assert expr == '"agre"* OR "id"'


def test_match_expression_cannot_inject_fts_operators():
    # Tokenisation strips every FTS5 metacharacter before quoting, so the
    # result is only quoted terms joined by OR.
    terms = text.topic_terms('NEAR("x" y) OR -z: * AND "unbalanced')
    expr = text.fts_match_expression(terms)
    assert re.fullmatch(r'("[^"\W_]+"\*? OR )*"[^"\W_]+"\*?', expr)


def test_empty_terms_give_no_expression():
    assert text.fts_match_expression([]) is None


def test_month_and_year_gives_that_month():
    start, end, tokens = text.date_range_hint("What was reported in September 2024?")
    assert (start, end) == ("2024-09-01", "2024-10-01")
    assert tokens == {"september", "2024"}


def test_december_rolls_the_year():
    assert text.date_range_hint("changes in December 2025")[:2] == ("2025-12-01", "2026-01-01")


def test_bare_year_gives_that_year_and_no_hint_gives_none():
    assert text.date_range_hint("figures for 2025")[:2] == ("2025-01-01", "2026-01-01")
    assert text.date_range_hint("What happened at the kickoff?") is None


def test_several_dates_span_the_window():
    assert text.date_range_hint("from March 2024 to June 2024")[:2] == ("2024-03-01", "2024-07-01")


def test_a_question_asking_for_figures_also_searches_percent():
    assert "percent" in text.topic_terms("Give every figure reported")
    assert "percent" in text.topic_terms("What proportion of articles were complete?")
    assert "percent" not in text.topic_terms("Who attended the kickoff?")


@pytest.mark.parametrize(
    "query",
    [
        "What proportion of articles were populated? Give every figure in the archive.",
        "Is bakery inside the fresh workstream? Show how the answer changed over time.",
        "How did the decision change?",
        "List all the meetings where retention was discussed.",
        "Show the trail from the agreement to the present.",
    ],
)
def test_enumerative_questions_are_recognised(query):
    from app.retrieval.text import is_enumerative_query

    assert is_enumerative_query(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "Who signed the UAT document?",
        "What service levels were agreed for ordering?",
        "Did Acme sign off UAT for the programme?",
        "Is the nightly extract still failing?",
    ],
)
def test_ordinary_questions_are_not_enumerative(query):
    from app.retrieval.text import is_enumerative_query

    assert is_enumerative_query(query) is False
