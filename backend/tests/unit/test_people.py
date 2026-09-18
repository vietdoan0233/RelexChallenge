from app.core.enums import DocumentType, PersonRelation
from app.db import repository
from app.ingestion import people
from app.ingestion.models import ParsedDocument, ParsedUnit
from app.schemas.evidence import Document, EvidenceUnit


def _doc(
    document_type: str, units: list[ParsedUnit], attendees: list[str] | None = None
) -> ParsedDocument:
    return ParsedDocument(
        document_id="doc1",
        filename="doc1.txt",
        document_type=document_type,
        title=None,
        source_date=None,
        thread_context=None,
        units=units,
        attendees=attendees or [],
    )


def _seed_evidence_unit(conn, evidence_id: str, raw_text: str) -> None:
    # evidence_people has a foreign key on evidence_units; link_mentions
    # against an evidence_id that was never actually ingested isn't a
    # real scenario, so these tests seed the minimum row that satisfies it.
    repository.upsert_document(
        conn, Document(document_id="doc1", filename="doc1.txt", document_type=DocumentType.EMAIL)
    )
    repository.insert_evidence_unit(
        conn,
        EvidenceUnit(
            evidence_id=evidence_id,
            document_id="doc1",
            source_locator="loc0",
            unit_index=0,
            raw_text=raw_text,
            text_hash="hash",
        ),
    )


def test_seeds_people_from_structural_sender_and_email(conn):
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
    report = people.seed_and_discover(conn, docs)
    assert report.people_count == 1
    person_id = repository.find_person_id_by_canonical_name(conn, "Ana Duarte")
    aliases = {
        row["alias"] for row in repository.all_aliases(conn) if row["person_id"] == person_id
    }
    assert "Ana Duarte" in aliases
    assert "ana@example.com" in aliases


def test_ambiguous_first_name_stays_unresolved(conn):
    # The corpus itself contains this exact ambiguity: a Nadia Haddad and
    # a Nadia Öberg. "Nadia" must never become an alias for either.
    docs = [
        _doc("EMAIL", [ParsedUnit(raw_text="a", speaker_sender="Nadia Haddad")]),
        _doc(
            "TRANSCRIPT",
            [ParsedUnit(raw_text="Nadia Öberg did something similar.", speaker_sender=None)],
        ),
    ]
    report = people.seed_and_discover(conn, docs)
    assert "Nadia" in report.unresolved_candidates
    matches = repository.find_person_ids_by_alias(conn, "Nadia")
    assert matches == []


def test_unambiguous_last_name_is_promoted_to_an_alias(conn):
    docs = [_doc("EMAIL", [ParsedUnit(raw_text="a", speaker_sender="Marco Rossi")])]
    people.seed_and_discover(conn, docs)
    matches = repository.find_person_ids_by_alias(conn, "Rossi")
    assert len(matches) == 1


def test_text_only_mention_of_a_never_speaking_person_still_becomes_a_person(conn):
    # e.g. Tobias Ekström: a departed employee mentioned once, never a
    # speaker or sender anywhere in the archive.
    docs = [
        _doc(
            "TRANSCRIPT",
            [
                ParsedUnit(
                    raw_text="We lost Tobias Ekström in January.", speaker_sender="Sofia Almeida"
                )
            ],
            attendees=["Sofia Almeida"],
        )
    ]
    report = people.seed_and_discover(conn, docs)
    assert "Tobias Ekström" in report.text_only_mentions
    assert repository.find_person_id_by_canonical_name(conn, "Tobias Ekström") is not None


def test_job_titles_in_signature_blocks_are_not_mistaken_for_people(conn):
    docs = [
        _doc(
            "EMAIL",
            [
                ParsedUnit(
                    raw_text="Thanks.\n\nNadia Haddad\nSolution Consultant\n+46 76 552 30 18",
                    speaker_sender="Nadia Haddad",
                )
            ],
        )
    ]
    report = people.seed_and_discover(conn, docs)
    assert "Solution Consultant" not in report.text_only_mentions
    assert repository.find_person_id_by_canonical_name(conn, "Solution Consultant") is None


def test_repeated_word_disfluency_is_not_mistaken_for_a_name(conn):
    docs = [
        _doc("TRANSCRIPT", [ParsedUnit(raw_text="That That order is fine.", speaker_sender=None)])
    ]
    report = people.seed_and_discover(conn, docs)
    assert "That That" not in report.text_only_mentions


def test_mentioned_relation_links_a_person_named_in_the_text(conn):
    docs = [
        _doc(
            "TRANSCRIPT",
            [ParsedUnit(raw_text="Kwame Boateng looked into it.", speaker_sender="Sofia Almeida")],
            attendees=["Sofia Almeida", "Kwame Boateng"],
        )
    ]
    people.seed_and_discover(conn, docs)
    kwame_id = repository.find_person_id_by_canonical_name(conn, "Kwame Boateng")
    _seed_evidence_unit(conn, "EV-doc1-t0", "Kwame Boateng looked into it.")
    linked = people.link_mentions(
        conn, "EV-doc1-t0", "Kwame Boateng looked into it.", exclude=set()
    )
    assert linked == 1
    rows = repository.evidence_people_for(conn, "EV-doc1-t0")
    assert (kwame_id, PersonRelation.MENTIONED.value) in [
        (r["person_id"], r["relation"]) for r in rows
    ]


def test_speaker_is_excluded_from_their_own_mentioned_links(conn):
    docs = [_doc("EMAIL", [ParsedUnit(raw_text="Ana Duarte here.", speaker_sender="Ana Duarte")])]
    people.seed_and_discover(conn, docs)
    ana_id = repository.find_person_id_by_canonical_name(conn, "Ana Duarte")
    _seed_evidence_unit(conn, "EV-doc1-m0", "Ana Duarte here.")
    linked = people.link_mentions(conn, "EV-doc1-m0", "Ana Duarte here.", exclude={ana_id})
    assert linked == 0
