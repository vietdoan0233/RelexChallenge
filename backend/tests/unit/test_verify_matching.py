"""How the verifier matches tracked identifiers: whole tokens for bare names, else substrings."""

from app.privacy import verify


def _count(text: str, *needles: str) -> int:
    return verify._contains(text.encode("utf-8"), list(needles))


def test_a_bare_name_token_matches_only_as_a_whole_token():
    assert _count("Ana said hello", "Ana") == 1
    assert _count("the management analysis of a banana", "Ana") == 0


def test_whole_token_matching_still_catches_punctuation_and_possessives():
    assert _count("Ana, Ana's report, and (Ana).", "ana") == 3
    assert _count("Boateng-Smith joined", "boateng") == 1


def test_a_hyphenated_or_apostrophe_name_is_one_token():
    assert _count("O'Brien and o\u2019brien", "O'Brien", "O\u2019Brien") == 2
    assert _count("Anne-Marie called", "Anne-Marie") == 1


def test_emails_and_multi_word_names_keep_strict_substring_matching():
    assert (
        _count("mail k.boateng@relexsolutions.example now", "k.boateng@relexsolutions.example") == 1
    )
    assert _count("xxKwame Boatengxx", "Kwame Boateng") == 1  # multi-word: substring


def test_matching_is_case_insensitive_and_unicode_aware():
    assert _count("ÖBERG and öberg", "Öberg") == 2
