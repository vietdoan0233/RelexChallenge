import json

import pytest

from app.core.enums import DocumentType, PersonRelation
from app.db import repository
from app.ingestion import people
from app.ingestion.models import ParsedDocument, ParsedUnit
from app.ingestion.people import ManifestValidationError, _observed_independently
from app.schemas.evidence import Document, EvidenceUnit


def _doc(document_type, units, attendees=None, document_id="doc1"):
    return ParsedDocument(
        document_id=document_id,
        filename=f"{document_id}.txt",
        document_type=document_type,
        title=None,
        source_date=None,
        thread_context=None,
        units=units,
        attendees=attendees or [],
    )


def _write_manifest(tmp_path, entries):
    manifest = {"description": "test manifest", "entries": entries}
    (tmp_path / "reviewed_identities.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def _identity_entry(canonical_name, review_note="Reviewed for this test.", verified_aliases=None):
    return {
        "canonical_name": canonical_name,
        "review_note": review_note,
        "verified_aliases": verified_aliases or [],
    }


def _seed_evidence_unit(conn, evidence_id, raw_text, document_id="doc1"):
    # evidence_people has a foreign key on evidence_units; link_mentions
    # against an evidence_id that was never actually ingested isn't a
    # real scenario, so these tests seed the minimum row that satisfies it.
    repository.upsert_document(
        conn,
        Document(
            document_id=document_id, filename=f"{document_id}.txt", document_type=DocumentType.EMAIL
        ),
    )
    repository.insert_evidence_unit(
        conn,
        EvidenceUnit(
            evidence_id=evidence_id,
            document_id=document_id,
            source_locator="loc0",
            unit_index=0,
            raw_text=raw_text,
            text_hash="hash",
        ),
    )


# ------------------------------------------------ structural confirmation


def test_named_transcript_speaker_is_a_confirmed_person(conn, tmp_path):
    docs = [
        _doc(
            "TRANSCRIPT",
            [ParsedUnit(raw_text="Hi", speaker_sender="Marco Rossi")],
            attendees=["Marco Rossi"],
        )
    ]
    people.seed_and_discover(conn, docs, tmp_path)
    assert repository.find_person_id_by_canonical_name(conn, "Marco Rossi") is not None


def test_email_sender_is_confirmed_and_address_linked(conn, tmp_path):
    docs = [
        _doc(
            "EMAIL",
            [
                ParsedUnit(
                    raw_text="Hi", speaker_sender="Ana Duarte", speaker_email="ana@example.com"
                )
            ],
        )
    ]
    people.seed_and_discover(conn, docs, tmp_path)
    person_id = repository.find_person_id_by_canonical_name(conn, "Ana Duarte")
    assert person_id is not None
    aliases = {
        row["alias"] for row in repository.all_aliases(conn) if row["person_id"] == person_id
    }
    assert "Ana Duarte" in aliases
    assert "ana@example.com" in aliases


# -------------------------------------------------------------- anonymity


def test_anonymous_me_and_them_never_become_people(conn, tmp_path):
    docs = [
        _doc(
            "TRANSCRIPT",
            [
                ParsedUnit(raw_text="First.", speaker_sender="Me"),
                ParsedUnit(raw_text="Second.", speaker_sender="Them"),
            ],
        )
    ]
    people.seed_and_discover(conn, docs, tmp_path)
    assert repository.find_person_id_by_canonical_name(conn, "Me") is None
    assert repository.find_person_id_by_canonical_name(conn, "Them") is None


def test_unknown_speaker_label_never_becomes_a_person(conn, tmp_path):
    docs = [
        _doc(
            "TRANSCRIPT", [ParsedUnit(raw_text="You're on mute.", speaker_sender="Unknown Speaker")]
        )
    ]
    people.seed_and_discover(conn, docs, tmp_path)
    assert repository.find_person_id_by_canonical_name(conn, "Unknown Speaker") is None


def test_confirmed_person_named_inside_anonymous_text_can_be_mentioned(conn, tmp_path):
    docs = [
        _doc(
            "EMAIL",
            [
                ParsedUnit(
                    raw_text="Hi", speaker_sender="Kwame Boateng", speaker_email="k@example.com"
                )
            ],
            document_id="doc-sender",
        ),
        _doc(
            "TRANSCRIPT",
            [ParsedUnit(raw_text="Kwame told me the extraction succeeded.", speaker_sender="Me")],
            document_id="doc-anon",
        ),
    ]
    people.seed_and_discover(conn, docs, tmp_path)
    kwame_id = repository.find_person_id_by_canonical_name(conn, "Kwame Boateng")
    assert kwame_id is not None

    _seed_evidence_unit(
        conn, "EV-1", "Kwame told me the extraction succeeded.", document_id="doc-anon"
    )
    linked = people.link_mentions(
        conn, "EV-1", "Kwame told me the extraction succeeded.", exclude=set()
    )
    assert linked == 1
    rows = repository.evidence_people_for(conn, "EV-1")
    assert (kwame_id, PersonRelation.MENTIONED.value) in [
        (r["person_id"], r["relation"]) for r in rows
    ]


# ------------------------------------------- free text never becomes people


def test_arbitrary_capitalized_span_never_becomes_a_person(conn, tmp_path):
    docs = [
        _doc(
            "TRANSCRIPT",
            [
                ParsedUnit(
                    raw_text="Risk Fresh Phase two is now behind schedule.", speaker_sender=None
                )
            ],
        )
    ]
    report = people.seed_and_discover(conn, docs, tmp_path)
    assert repository.find_person_id_by_canonical_name(conn, "Risk Fresh Phase") is None
    assert "Risk Fresh Phase" in report.rejected_candidates


def test_known_false_positive_phrases_are_never_stored_as_people_or_aliases(conn, tmp_path):
    # The exact contamination this hardening pass exists to fix.
    texts = [
        "Risk Fresh Phase two slipped again this week.",
        "Risk Still open from four updates ago.",
        "Slight Delay Bakery recommendation is to descope.",
        "That That order is fine but I want to say something.",
        "This So far has been the only workaround we have found.",
        "Not Nadia Öberg, the other one.",
        "Hi All, hereby the weekly update.",
        "Data Protection Officer signed off the DPA review.",
        "Chief Financial Officer approved the budget line.",
    ]
    docs = [_doc("TRANSCRIPT", [ParsedUnit(raw_text=t, speaker_sender=None) for t in texts])]
    people.seed_and_discover(conn, docs, tmp_path)

    rejected_names = {
        "Risk Fresh Phase",
        "Risk Still",
        "Slight Delay Bakery",
        "Bakery",
        "This So",
        "Not Nadia Öberg",
        "Hi All",
        "Data Protection Officer",
        "Chief Financial Officer",
    }
    for name in rejected_names:
        assert repository.find_person_id_by_canonical_name(conn, name) is None, name
    all_aliases = {row["alias"] for row in repository.all_aliases(conn)}
    assert not (rejected_names & all_aliases)
    assert "Bakery" not in all_aliases


# --------------------------------------------- reviewed text-only identity


def test_text_only_mention_is_rejected_without_a_reviewed_manifest_entry(conn, tmp_path):
    docs = [
        _doc(
            "TRANSCRIPT",
            [
                ParsedUnit(
                    raw_text="Tobias Ekström did chilled before he left.",
                    speaker_sender="Sofia Almeida",
                )
            ],
            attendees=["Sofia Almeida"],
        )
    ]
    report = people.seed_and_discover(conn, docs, tmp_path)  # no manifest file in tmp_path
    assert repository.find_person_id_by_canonical_name(conn, "Tobias Ekström") is None
    assert "Tobias Ekström" in report.rejected_candidates


def test_reviewed_manifest_entry_becomes_a_confirmed_person(conn, tmp_path):
    _write_manifest(
        tmp_path,
        [_identity_entry("Tobias Ekström", "Mentioned once; departed employee.")],
    )
    docs = [
        _doc(
            "TRANSCRIPT",
            [
                ParsedUnit(
                    raw_text="Tobias Ekström did chilled before he left.",
                    speaker_sender="Sofia Almeida",
                )
            ],
            attendees=["Sofia Almeida"],
        )
    ]
    report = people.seed_and_discover(conn, docs, tmp_path)
    assert repository.find_person_id_by_canonical_name(conn, "Tobias Ekström") is not None
    assert "Tobias Ekström" in report.reviewed_text_only


def test_nadia_haddad_and_nadia_oberg_are_separate_confirmed_people(conn, tmp_path):
    _write_manifest(
        tmp_path,
        [_identity_entry("Nadia Öberg", "Distinguished from a different same-first-name person.")],
    )
    docs = [
        _doc(
            "EMAIL", [ParsedUnit(raw_text="a", speaker_sender="Nadia Haddad")], document_id="doc-a"
        ),
        _doc(
            "TRANSCRIPT",
            [
                ParsedUnit(
                    raw_text="Nadia Haddad, employee four. Not Nadia Öberg.", speaker_sender=None
                )
            ],
            document_id="doc-b",
        ),
    ]
    report = people.seed_and_discover(conn, docs, tmp_path)

    haddad_id = repository.find_person_id_by_canonical_name(conn, "Nadia Haddad")
    oberg_id = repository.find_person_id_by_canonical_name(conn, "Nadia Öberg")
    assert haddad_id is not None
    assert oberg_id is not None
    assert haddad_id != oberg_id

    # "Not Nadia Öberg" must never itself become a person, and a bare
    # "Nadia" must remain unresolved between the two.
    assert repository.find_person_id_by_canonical_name(conn, "Not Nadia Öberg") is None
    assert "Nadia" in report.unresolved_alias_candidates
    assert repository.find_person_ids_by_alias(conn, "Nadia") == []


# -------------------------------------------------------- alias promotion


def test_unique_first_name_inside_its_own_full_name_is_not_promoted(conn, tmp_path):
    # Regression test for the exact bug this pass fixes: "Ahmed" only ever
    # occurs as part of "Ahmed Nasser" itself, never standalone. An earlier
    # version of the independence check only looked *backward* from a
    # candidate's match, so a first name (whose full name lies *ahead* of
    # it) was wrongly treated as independently observed. It must not be
    # promoted regardless -- uniqueness/observation are no longer
    # promotion criteria at all, only reviewed-alias-manifest entries are.
    docs = [
        _doc(
            "EMAIL",
            [ParsedUnit(raw_text="Hello from the team.", speaker_sender="Ahmed Nasser")],
        )
    ]
    report = people.seed_and_discover(conn, docs, tmp_path)
    assert repository.find_person_ids_by_alias(conn, "Ahmed") == []
    assert "Ahmed" in report.unresolved_alias_candidates


def test_unique_last_name_inside_its_own_full_name_is_not_promoted(conn, tmp_path):
    # "Rossi" is derivable from "Marco Rossi" but never used on its own
    # anywhere in this corpus fixture -- it must stay unresolved.
    docs = [
        _doc("EMAIL", [ParsedUnit(raw_text="Hello from the team.", speaker_sender="Marco Rossi")])
    ]
    report = people.seed_and_discover(conn, docs, tmp_path)
    assert repository.find_person_ids_by_alias(conn, "Rossi") == []
    assert "Rossi" in report.unresolved_alias_candidates


def test_independently_observed_short_token_is_not_auto_promoted_without_review(conn, tmp_path):
    # "Rossi" here IS used standalone, not just as part of "Marco Rossi" --
    # but independent corpus usage alone is still not proof it refers to
    # Marco Rossi specifically. Without a reviewed manifest entry it must
    # stay unresolved, not be automatically promoted.
    docs = [
        _doc(
            "EMAIL",
            [
                ParsedUnit(raw_text="Hello from the team.", speaker_sender="Marco Rossi"),
                ParsedUnit(raw_text="Rossi confirmed the numbers separately.", speaker_sender=None),
            ],
        )
    ]
    report = people.seed_and_discover(conn, docs, tmp_path)
    assert repository.find_person_ids_by_alias(conn, "Rossi") == []
    assert "Rossi" in report.unresolved_alias_candidates


def test_reviewed_short_alias_with_evidence_is_accepted(conn, tmp_path):
    _write_manifest(
        tmp_path,
        [
            _identity_entry(
                "Marco Rossi",
                "Signed a follow-up email using only the last name.",
                verified_aliases=[
                    {
                        "alias": "Rossi",
                        "alias_type": "LAST_NAME",
                        "source_reference": "emails/09 follow-up, signed 'Rossi'",
                    }
                ],
            )
        ],
    )
    docs = [
        _doc(
            "EMAIL",
            [ParsedUnit(raw_text="Hello from the team.", speaker_sender="Marco Rossi")],
        )
    ]
    report = people.seed_and_discover(conn, docs, tmp_path)

    rossi_id = repository.find_person_id_by_canonical_name(conn, "Marco Rossi")
    assert repository.find_person_ids_by_alias(conn, "Rossi") == [rossi_id]
    alias_types = {
        row["alias_type"]
        for row in repository.all_aliases(conn)
        if row["person_id"] == rossi_id and row["alias"] == "Rossi"
    }
    assert alias_types == {"LAST_NAME"}
    assert "Rossi" not in report.unresolved_alias_candidates
    assert any("Rossi" in entry for entry in report.reviewed_short_aliases)
    # This manifest entry only reviews an alias for an already-structural
    # person; it must not be double-counted as a text-only identity.
    assert "Marco Rossi" not in report.reviewed_text_only


def test_ambiguous_alias_stays_unresolved_even_if_independently_observed(conn, tmp_path):
    docs = [
        _doc(
            "EMAIL", [ParsedUnit(raw_text="a", speaker_sender="Marco Rossi")], document_id="doc-a"
        ),
        _doc("EMAIL", [ParsedUnit(raw_text="b", speaker_sender="Anna Rossi")], document_id="doc-b"),
        _doc(
            "TRANSCRIPT",
            [ParsedUnit(raw_text="Rossi will follow up separately.", speaker_sender=None)],
            document_id="doc-c",
        ),
    ]
    report = people.seed_and_discover(conn, docs, tmp_path)
    assert repository.find_person_ids_by_alias(conn, "Rossi") == []
    assert "Rossi" in report.unresolved_alias_candidates


# --------------------------------------------------------------- mentions


def test_unique_first_name_mention_is_recognized_without_being_a_stored_alias(conn, tmp_path):
    # MENTIONED-detection and deletion-relevant alias promotion are
    # different concerns: CLAUDE.md requires that a confirmed person
    # explicitly named inside text may still be MENTIONED, and in
    # practice that is often just a first name. This must work even
    # though "Kwame" itself is never written to person_aliases.
    docs = [
        _doc(
            "EMAIL",
            [ParsedUnit(raw_text="Hi", speaker_sender="Kwame Boateng", speaker_email="k@x.com")],
            document_id="doc-sender",
        ),
        _doc(
            "TRANSCRIPT",
            [ParsedUnit(raw_text="Kwame told me the extraction succeeded.", speaker_sender="Me")],
            document_id="doc-anon",
        ),
    ]
    people.seed_and_discover(conn, docs, tmp_path)
    kwame_id = repository.find_person_id_by_canonical_name(conn, "Kwame Boateng")
    assert repository.find_person_ids_by_alias(conn, "Kwame") == []

    _seed_evidence_unit(
        conn, "EV-2", "Kwame told me the extraction succeeded.", document_id="doc-anon"
    )
    linked = people.link_mentions(
        conn, "EV-2", "Kwame told me the extraction succeeded.", exclude=set()
    )
    assert linked == 1
    rows = repository.evidence_people_for(conn, "EV-2")
    assert (kwame_id, PersonRelation.MENTIONED.value) in [
        (r["person_id"], r["relation"]) for r in rows
    ]


def test_ambiguous_first_name_is_not_guessed_for_mentions(conn, tmp_path):
    docs = [
        _doc(
            "EMAIL", [ParsedUnit(raw_text="a", speaker_sender="Nadia Haddad")], document_id="doc-a"
        ),
    ]
    _write_manifest(
        tmp_path,
        [_identity_entry("Nadia Öberg", "Distinguished from a different same-first-name person.")],
    )
    docs.append(
        _doc(
            "TRANSCRIPT",
            [ParsedUnit(raw_text="Nadia will follow up tomorrow.", speaker_sender=None)],
            document_id="doc-b",
        )
    )
    people.seed_and_discover(conn, docs, tmp_path)

    _seed_evidence_unit(conn, "EV-3", "Nadia will follow up tomorrow.", document_id="doc-b")
    linked = people.link_mentions(conn, "EV-3", "Nadia will follow up tomorrow.", exclude=set())
    assert linked == 0


def test_speaker_is_excluded_from_their_own_mentioned_links(conn, tmp_path):
    docs = [_doc("EMAIL", [ParsedUnit(raw_text="Ana Duarte here.", speaker_sender="Ana Duarte")])]
    people.seed_and_discover(conn, docs, tmp_path)
    ana_id = repository.find_person_id_by_canonical_name(conn, "Ana Duarte")
    _seed_evidence_unit(conn, "EV-doc1-m0", "Ana Duarte here.")
    linked = people.link_mentions(conn, "EV-doc1-m0", "Ana Duarte here.", exclude={ana_id})
    assert linked == 0


# ------------------------------------------------ _observed_independently


def test_observed_independently_first_name_inside_its_own_full_name_is_false():
    # The exact bug: a backward-only search window found the full name
    # when the candidate was the *last* word (full name lies behind it)
    # but missed it when the candidate was the *first* word (full name
    # lies ahead of it), wrongly returning True here.
    assert _observed_independently("Ahmed", "Ahmed Nasser", "Ahmed Nasser") is False


def test_observed_independently_last_name_inside_its_own_full_name_is_false():
    assert _observed_independently("Rossi", "Marco Rossi", "Marco Rossi") is False


def test_observed_independently_true_for_genuine_standalone_use():
    text = "Marco Rossi opened the call. Later, Rossi confirmed the numbers separately."
    assert _observed_independently("Rossi", "Marco Rossi", text) is True


# ------------------------------------------------------ manifest validation


def test_manifest_missing_canonical_name_raises(tmp_path):
    _write_manifest(tmp_path, [{"review_note": "no name given"}])
    with pytest.raises(ManifestValidationError):
        people.load_reviewed_identities(tmp_path)


def test_manifest_missing_review_note_raises(tmp_path):
    _write_manifest(tmp_path, [{"canonical_name": "Someone Reviewed"}])
    with pytest.raises(ManifestValidationError):
        people.load_reviewed_identities(tmp_path)


def test_manifest_duplicate_canonical_name_raises(tmp_path):
    _write_manifest(
        tmp_path,
        [_identity_entry("Someone Reviewed"), _identity_entry("Someone Reviewed")],
    )
    with pytest.raises(ManifestValidationError):
        people.load_reviewed_identities(tmp_path)


def test_manifest_duplicate_alias_across_entries_raises(tmp_path):
    alias = [{"alias": "shared@example.com", "alias_type": "EMAIL", "source_reference": "x"}]
    _write_manifest(
        tmp_path,
        [
            _identity_entry("Person One", verified_aliases=alias),
            _identity_entry("Person Two", verified_aliases=alias),
        ],
    )
    with pytest.raises(ManifestValidationError):
        people.load_reviewed_identities(tmp_path)


def test_manifest_unsupported_alias_type_raises(tmp_path):
    _write_manifest(
        tmp_path,
        [
            _identity_entry(
                "Someone Reviewed",
                verified_aliases=[
                    {"alias": "Someone", "alias_type": "ROLE", "source_reference": "x"}
                ],
            )
        ],
    )
    with pytest.raises(ManifestValidationError):
        people.load_reviewed_identities(tmp_path)


def test_manifest_empty_alias_value_raises(tmp_path):
    _write_manifest(
        tmp_path,
        [
            _identity_entry(
                "Someone Reviewed",
                verified_aliases=[{"alias": "   ", "alias_type": "EMAIL", "source_reference": "x"}],
            )
        ],
    )
    with pytest.raises(ManifestValidationError):
        people.load_reviewed_identities(tmp_path)


def test_manifest_full_name_alias_type_is_rejected(tmp_path):
    # FULL_NAME is always assigned automatically from canonical_name; a
    # manifest entry redeclaring it would be a second, driftable source
    # of truth for the same fact.
    _write_manifest(
        tmp_path,
        [
            _identity_entry(
                "Someone Reviewed",
                verified_aliases=[
                    {
                        "alias": "Someone Reviewed",
                        "alias_type": "FULL_NAME",
                        "source_reference": "x",
                    }
                ],
            )
        ],
    )
    with pytest.raises(ManifestValidationError):
        people.load_reviewed_identities(tmp_path)
