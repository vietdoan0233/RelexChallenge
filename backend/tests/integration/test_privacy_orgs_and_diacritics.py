"""Organisation-preserving anonymization and diacritic-variant names.

Regression tests for two things a full-archive purge sweep found: a person the
archive spells both "Henrik Sørensen" and "Henrik Sorensen" crashed the purge
(and locked the app), and redaction erased *who the person spoke for*.

All instances are temporary (CLAUDE.md 0.5)."""

import json

from app.db.connection import connect
from app.ingestion.embeddings import MockEmbeddingProvider
from app.ingestion.service import ingest
from app.privacy import ops, orgs, redact, service, verify
from app.privacy.targets import Target, fold, name_pattern

TEAMS = (
    "Meeting: Commercial review\nCustomer: Acme Org\nDate: 2024-06-11\nPhase: Presales\n"
    "Attendees: Marco Rossi (RELEX), Henrik Sørensen (RELEX Account Director), "
    "Lena Fischer (Acme)\n\n"
    "Marco Rossi\n0:050:05\nMR\nMarco Rossi 5 seconds\n"
    "Henrik, this is the price we discussed.\n"
    "Henrik Sørensen\n0:100:10\nHS\nHenrik Sorensen 10 seconds\n"
    "We can hold the price until the end of the quarter.\n"
    "Lena Fischer\n0:150:15\nLF\nLena Fischer 15 seconds\n"
    "That works for us.\n"
)
EMAIL = (
    "Subject: Pricing\n"
    "From: Henrik Sørensen <henrik.sorensen@relexsolutions.example>\n"
    "Date: Monday, June 3, 2024 10:00\n"
    "To: Lena Fischer <lena.fischer@acme-org.example>\n"
    "Messages in thread: 1\n\n"
    "Price is held until the end of the quarter.\n"
)
OTHER_EMAIL = (
    "Subject: Hello\n"
    "From: Marco Rossi <marco.rossi@relexsolutions.example>\n"
    "Date: Monday, June 3, 2024 09:00\n"
    "To: Lena Fischer <lena.fischer@acme-org.example>\n"
    "Messages in thread: 1\n\n"
    "Welcome.\n"
)


def _instance(tmp_path):
    source = tmp_path / "source"
    for sub in ("transcripts", "emails", "reports"):
        (source / sub).mkdir(parents=True)
    (source / "transcripts" / "01_pricing.txt").write_text(TEAMS, encoding="utf-8")
    (source / "emails" / "01_price-hold.txt").write_text(EMAIL, encoding="utf-8")
    (source / "emails" / "02_hello.txt").write_text(OTHER_EMAIL, encoding="utf-8")
    (source / "reviewed_identities.json").write_text(
        json.dumps({"description": "t", "entries": []}), encoding="utf-8"
    )
    conn = connect(str(tmp_path / "app.db"))
    provider = MockEmbeddingProvider()
    ingest(conn, source, provider)
    return source, conn, provider


def _purge(tmp_path, source, conn, provider, person_id):
    return service.purge(
        conn,
        source_dir=source,
        db_path=tmp_path / "app.db",
        ops_dir=tmp_path / "privacy_ops",
        person_id=person_id,
        artifact_dirs=[],
        provider=provider,
    )


def test_name_pattern_and_verifier_treat_diacritic_spellings_as_one_name():
    pattern = name_pattern("Henrik Sørensen")
    for spelling in ("Henrik Sørensen", "henrik sorensen", "HENRIK  SORENSEN"):
        assert pattern.search(spelling)
    assert not pattern.search("Henrik Sorensens")
    assert fold("Nadia Öberg") == "nadia oberg"
    assert verify._contains(b"Henrik Sorensen was here", ["Henrik Sørensen"]) == 1


def test_purge_of_a_person_spelled_two_ways_completes_and_leaves_no_variant(tmp_path):
    source, conn, provider = _instance(tmp_path)
    ids = {r[0] for r in conn.execute("SELECT evidence_id FROM evidence_units")}
    result = _purge(tmp_path, source, conn, provider, "henrik-s-rensen")
    assert result.verified
    text = "\n".join(p.read_text(encoding="utf-8") for p in source.rglob("*.txt")).lower()
    assert "sørensen" not in text and "sorensen" not in text
    assert {r[0] for r in conn.execute("SELECT evidence_id FROM evidence_units")} == ids
    assert not ops.is_locked(tmp_path / "privacy_ops")


def test_the_organisation_survives_as_an_anonymous_hint_but_the_title_does_not(tmp_path):
    source, conn, provider = _instance(tmp_path)
    _purge(tmp_path, source, conn, provider, "henrik-s-rensen")
    teams = (source / "transcripts" / "01_pricing.txt").read_text(encoding="utf-8")
    assert "[REDACTED PERSON: RELEX]" in teams
    assert "[REDACTED SPEAKER: RELEX] 10 seconds" in teams
    assert "Account Director" not in teams
    email = (source / "emails" / "01_price-hold.txt").read_text(encoding="utf-8")
    assert "From: [REDACTED SENDER: RELEX]" in email
    speakers = {r[0] for r in conn.execute("SELECT speaker_sender FROM evidence_units")}
    assert "[REDACTED SPEAKER: RELEX]" in speakers
    assert "[REDACTED SENDER: RELEX]" in speakers
    # A tagged marker is never mistaken for a person.
    assert not conn.execute(
        "SELECT 1 FROM people WHERE canonical_name LIKE '%REDACTED%'"
    ).fetchone()


def test_the_organisation_follows_the_person_when_they_change_jobs():
    target = Target("p", "Ana Lima", ("Ana Lima",), ())
    ctx = orgs.OrgContext(vocabulary=frozenset({"RELEX", "Acme"}), default="RELEX")
    body = "\n\nAna Lima\n0:010:01\nAL\nAna Lima 1 second\nHi\n"
    old = "Attendees: Ana Lima (RELEX), Bo Ek (Acme)" + body
    new = "Attendees: Ana Lima (Acme), Bo Ek (Acme)" + body
    assert "[REDACTED SPEAKER: RELEX] 1 second" in redact.sanitize_text(
        old, "transcripts", target, ctx
    )
    assert "[REDACTED SPEAKER: Acme] 1 second" in redact.sanitize_text(
        new, "transcripts", target, ctx
    )


def test_without_a_known_organisation_the_generic_marker_is_used():
    target = Target("p", "Ana Lima", ("Ana Lima",), ())
    out = redact.sanitize_text("Ana Lima said hi.", "reports", target, orgs.OrgContext())
    assert out == "[REDACTED PERSON] said hi."
