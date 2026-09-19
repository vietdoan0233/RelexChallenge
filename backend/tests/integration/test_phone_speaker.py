"""A dial-in participant identified only by a phone number, or an
unlisted "Guest N", is a real, attributable speaker (its turns are
Evidence Units) but never a person: neither label may reach `people`, `person_aliases`, or
`evidence_people`, where a future deletion would treat it as an identity.
Exercised through the full ingest() path because the failure mode only
shows once people.seed_and_discover and service._link_relations both run.
"""

from pathlib import Path

from app.db import repository
from app.ingestion.service import ingest

_PHONE = "+358 40 5512 097"

_TRANSCRIPT = (
    "Meeting: Ordering logic design workshop\nCustomer: Acme Org\nDate: 2024-11-12\n"
    "Phase: Implementation\nAttendees: Marco Rossi (RELEX), Lena Fischer (Acme)\n\n"
    "Lena Fischer\n6:346:34\nLF\nLena Fischer 6 minutes 34 seconds\n"
    "Ninety-nine on everything, in theory, which is\n"
    f"{_PHONE}\n6:406:40\n+4\n{_PHONE} 6 minutes 40 seconds\nMm-hm.\n"
    "Lena Fischer\n6:446:44\nLF\nLena Fischer 6 minutes 44 seconds\n"
    "why we carry so much stock.\n"
    "Guest 1\n6:506:50\nG1\nGuest 1 6 minutes 50 seconds\nSounds right.\n"
)


def _write_corpus(root: Path) -> None:
    for sub in ("transcripts", "emails", "reports"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "transcripts" / "01_workshop.txt").write_text(_TRANSCRIPT, encoding="utf-8")


def test_unlisted_speaker_units_are_stored_but_never_become_people(tmp_path, conn):
    source = tmp_path / "source"
    _write_corpus(source)

    report = ingest(conn, source, embedding_provider=None)

    units = {row["raw_text"]: row for row in repository.all_evidence_units(conn)}
    assert set(units) == {
        "Ninety-nine on everything, in theory, which is",
        "Mm-hm.",
        "why we carry so much stock.",
        "Sounds right.",
    }
    dial_in = units["Mm-hm."]
    assert dial_in["speaker_sender"] == _PHONE
    guest = units["Sounds right."]
    assert guest["speaker_sender"] == "Guest 1"

    for label, unit in ((_PHONE, dial_in), ("Guest 1", guest)):
        assert repository.find_person_id_by_canonical_name(conn, label) is None
        assert label not in {row["alias"] for row in repository.all_aliases(conn)}
        assert label not in report.rejected_candidates
        assert label not in report.unresolved_alias_candidates
        assert repository.evidence_people_for(conn, unit["evidence_id"]) == []

    # Named speakers around the dial-in keep their normal SPEAKER links.
    lena_id = repository.find_person_id_by_canonical_name(conn, "Lena Fischer")
    assert lena_id is not None
    lena_unit = units["why we carry so much stock."]
    assert lena_id in [
        r["person_id"] for r in repository.evidence_people_for(conn, lena_unit["evidence_id"])
    ]
