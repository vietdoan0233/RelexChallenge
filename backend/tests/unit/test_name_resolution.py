"""Strict name -> subject assignment on the full-name, first-name, and
last-name bases."""

from app.db import repository
from app.ingestion import name_resolution as nr


def _person(conn, name, *aliases):
    subject_id = repository.get_or_create_subject(conn, name)
    repository.add_alias(conn, subject_id, name, "FULL_NAME")
    for alias, alias_type in aliases:
        repository.add_alias(conn, subject_id, alias, alias_type)
    return subject_id


def _index(conn, corpus=""):
    return nr.build_index(conn, corpus=corpus)


def test_full_name_and_first_name_resolve_to_the_same_subject(conn):
    ana = _person(conn, "Ana Duarte")
    index = _index(conn)

    full = index.resolve("Ana Duarte")
    first = index.resolve("Ana")

    assert full and full.subject_id == ana and full.basis == nr.FULL_NAME
    assert first and first.subject_id == ana and first.basis == nr.FIRST_NAME
    assert index.first_name_of(ana) == "Ana"


def test_resolution_ignores_case_whitespace_and_unicode_composition(conn):
    ana = _person(conn, "Ana Duarte")
    index = _index(conn)

    assert index.resolve("  ana   DUARTE ").subject_id == ana
    assert index.resolve("ANA").subject_id == ana


def test_a_first_name_shared_by_two_people_is_assigned_to_neither(conn):
    haddad = _person(conn, "Nadia Haddad")
    oberg = _person(conn, "Nadia Öberg")
    index = _index(conn)

    assert index.resolve("Nadia") is None
    assert index.first_name_of(haddad) is None and index.first_name_of(oberg) is None
    why = index.unassigned_first_name(haddad)
    assert (why.token, why.reason) == ("Nadia", "shared")
    # Their full names still resolve, each to the right person.
    assert index.resolve("Nadia Haddad").subject_id == haddad
    assert index.resolve("Nadia Öberg").subject_id == oberg


def test_a_first_name_that_is_someone_elses_last_name_is_not_assigned(conn):
    _person(conn, "Robert Kahn")
    other = _person(conn, "Sofia Robert")
    index = _index(conn)

    assert index.resolve("Robert") is None
    assert index.first_name_of(other) == "Sofia"


def test_an_everyday_word_used_as_a_first_name_is_not_assigned(conn):
    will = _person(conn, "Will Turner")
    index = _index(conn)

    assert index.resolve("Will") is None
    assert index.unassigned_first_name(will).reason == "ordinary-word"


def test_a_name_used_mostly_as_a_lowercase_word_is_not_assigned(conn):
    tomas = _person(conn, "Tomas Lindholm")
    corpus = "Tomas said so. and tomas tomas tomas. we asked tomas again."
    index = _index(conn, corpus=corpus)

    assert index.resolve("Tomas") is None
    assert index.unassigned_first_name(tomas).reason == "ordinary-word"


def test_lowercase_asr_captions_of_a_real_name_do_not_disqualify_it(conn):
    marco = _person(conn, "Marco Rossi")
    corpus = "Marco spoke. Then Marco again. Marco agreed. Well, marco. Okay."
    index = _index(conn, corpus=corpus)

    assert index.resolve("Marco").subject_id == marco


def test_an_email_local_part_is_not_a_lowercase_use_of_the_name(conn):
    ana = _person(conn, "Ana Duarte")
    corpus = "Reach ana.duarte@example.test or ana@example.test. Ana confirmed."
    index = _index(conn, corpus=corpus)

    assert index.resolve("Ana").subject_id == ana


def test_a_too_short_first_name_is_not_assigned(conn):
    jo = _person(conn, "Jo Smith")
    index = _index(conn)

    assert index.resolve("Jo") is None
    assert index.unassigned_first_name(jo).reason == "too-short"


def test_a_reviewed_first_name_alias_is_authoritative_even_if_shared(conn):
    haddad = _person(conn, "Nadia Haddad", ("Nadia", "FIRST_NAME"))
    _person(conn, "Nadia Öberg")
    index = _index(conn)

    assert index.resolve("Nadia").subject_id == haddad


# ------------------------------------------------------------- last name
#
# The identical strict basis as first name, added to close a gap where
# link_mentions() already auto-linked a bare last name as MENTIONED via a
# separate, looser check that the pseudonymisation target never consulted
# -- so a colleague's bare "Boateng" survived rewriting while the operation
# still reported full verified success. See this module's docstring.


def test_a_unique_last_name_is_assigned(conn):
    kwame = _person(conn, "Kwame Boateng")
    index = _index(conn)

    assert index.last_name_of(kwame) == "Boateng"


def test_a_last_name_shared_by_two_people_is_assigned_to_neither(conn):
    kwame = _person(conn, "Kwame Boateng")
    ama = _person(conn, "Ama Boateng")
    index = _index(conn)

    assert index.last_name_of(kwame) is None
    assert index.last_name_of(ama) is None
    # Their full names still resolve, each to the right person.
    assert index.resolve("Kwame Boateng").subject_id == kwame
    assert index.resolve("Ama Boateng").subject_id == ama


def test_a_last_name_that_is_someone_elses_first_name_is_not_assigned(conn):
    _person(conn, "Robert Kahn")
    other = _person(conn, "Sofia Robert")
    index = _index(conn)

    assert index.last_name_of(other) is None
    assert index.first_name_of(other) == "Sofia"


def test_an_everyday_word_used_as_a_last_name_is_not_assigned(conn):
    turner = _person(conn, "Ann Rose")
    index = _index(conn)

    assert index.last_name_of(turner) is None


def test_a_reviewed_last_name_alias_is_authoritative_even_if_shared(conn):
    kwame = _person(conn, "Kwame Boateng", ("Boateng", "LAST_NAME"))
    _person(conn, "Ama Boateng")
    index = _index(conn)

    assert index.last_name_of(kwame) == "Boateng"


def test_overlapping_surnames_are_not_confused_by_the_last_name_basis(conn):
    """ "Reed" is a literal prefix of "Reeder"/"Reedman", but _name_parts
    splits on whitespace only, so neither shares the word "reed" with Ann
    Reed -- her last name is still safely unique."""
    reed = _person(conn, "Ann Reed")
    _person(conn, "Joann Reeder")
    _person(conn, "Ann Reedman")
    index = _index(conn)

    assert index.last_name_of(reed) == "Reed"


def test_a_single_word_display_name_has_no_first_name_basis(conn):
    cher = _person(conn, "Cher")
    index = _index(conn)

    assert index.first_name_of(cher) is None
    assert index.resolve("Cher").subject_id == cher  # still a full-name match


def test_a_pseudonymised_subject_never_resolves_to_a_real_name(conn):
    ana = _person(conn, "Ana Duarte")
    conn.execute(
        "UPDATE people SET privacy_state = 'PSEUDONYMISED', display_name = NULL "
        "WHERE subject_id = ?",
        (ana,),
    )
    index = _index(conn)

    assert index.resolve("Ana") is None and index.resolve("Ana Duarte") is None


def test_a_display_alias_token_is_reserved(conn):
    ana = _person(conn, "Participant Hansen")
    conn.execute(
        "UPDATE people SET display_alias = 'Participant Q7M4-N8' WHERE subject_id = ?", (ana,)
    )
    index = _index(conn)

    assert index.resolve("Participant") is None


def test_fold_maps_a_bare_structural_name_onto_the_one_full_name():
    folded = nr.fold_single_word_names({"Ana", "Ana Duarte", "Marco Rossi"})
    assert folded == {"Ana": "Ana Duarte"}


def test_fold_refuses_an_ambiguous_or_unmatched_bare_name():
    assert nr.fold_single_word_names({"Nadia", "Nadia Haddad", "Nadia Öberg"}) == {}
    assert nr.fold_single_word_names({"Zed", "Ana Duarte"}) == {}
    assert nr.fold_single_word_names({"Me", "Them", "Ana Duarte"}) == {}
