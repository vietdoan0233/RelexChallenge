"""Locator revocation and revoked-locator collision behavior (CLAUDE.md
18.8): the tombstone-in-place primitive and ordinary ingestion's
awareness of it. This slice does not implement the privacy service that
will eventually decide which locators to revoke, and does not implement
or imply the pure replay resolver from CLAUDE.md 18.9 -- both remain
future work.
"""

import pytest

from app.db import repository
from app.ingestion import locator_manifest


def _seed_locator(conn, document_id, source_locator, fp, position):
    repository.record_source_locator(
        conn, document_id, source_locator, fp, position, "2024-01-01T00:00:00+00:00"
    )


# --------------------------------------------------------------- revocation


def test_revocation_preserves_locator_identity_and_genesis_position(conn):
    _seed_locator(conn, "doc1", "u0000", "fp-a", 0)
    repository.revoke_source_locator(conn, "doc1", "u0000", "2024-06-01T00:00:00+00:00")

    row = repository.find_locator_row(conn, "doc1", "u0000")
    assert row is not None
    assert row["genesis_position"] == 0
    still_present = conn.execute(
        "SELECT 1 FROM source_locators WHERE document_id = ? AND source_locator = ?",
        ("doc1", "u0000"),
    ).fetchone()
    assert still_present is not None


def test_revocation_replaces_the_fingerprint_with_the_sentinel(conn):
    _seed_locator(conn, "doc1", "u0000", "fp-a", 0)
    repository.revoke_source_locator(conn, "doc1", "u0000", "2024-06-01T00:00:00+00:00")

    row = conn.execute(
        "SELECT content_fingerprint FROM source_locators "
        "WHERE document_id = ? AND source_locator = ?",
        ("doc1", "u0000"),
    ).fetchone()
    assert row["content_fingerprint"] == repository.REVOKED_FINGERPRINT_SENTINEL
    assert row["content_fingerprint"] != "fp-a"


def test_revocation_sets_revoked_at(conn):
    _seed_locator(conn, "doc1", "u0000", "fp-a", 0)
    repository.revoke_source_locator(conn, "doc1", "u0000", "2024-06-01T00:00:00+00:00")

    row = repository.find_locator_row(conn, "doc1", "u0000")
    assert row["revoked_at"] == "2024-06-01T00:00:00+00:00"


def test_repeated_revocation_is_idempotent_and_preserves_original_timestamp(conn):
    _seed_locator(conn, "doc1", "u0000", "fp-a", 0)
    repository.revoke_source_locator(conn, "doc1", "u0000", "2024-06-01T00:00:00+00:00")
    repository.revoke_source_locator(conn, "doc1", "u0000", "2024-12-31T00:00:00+00:00")

    row = repository.find_locator_row(conn, "doc1", "u0000")
    assert row["revoked_at"] == "2024-06-01T00:00:00+00:00"


def test_revoking_an_unassigned_locator_raises_not_found(conn):
    with pytest.raises(repository.LocatorNotFoundError):
        repository.revoke_source_locator(conn, "doc1", "u9999", "2024-06-01T00:00:00+00:00")


# ---------------------------------------------- manifest-generated locators


def test_revoked_rows_are_excluded_from_fingerprint_matching(conn):
    _seed_locator(conn, "doc1", "u0000", "fp-a", 0)
    repository.revoke_source_locator(conn, "doc1", "u0000", "2024-06-01T00:00:00+00:00")

    # A new fragment with the SAME original fingerprint must not match
    # the revoked row -- it must mint a fresh locator instead.
    [assignment] = locator_manifest.assign_manifest_locators(conn, "doc1", ["fp-a"])
    assert assignment.source_locator != "u0000"
    assert assignment.genesis_position > 0


def test_revoking_the_highest_generated_locator_prevents_its_reuse(conn):
    [a0] = locator_manifest.assign_manifest_locators(conn, "doc1", ["fp-a"])
    [a1] = locator_manifest.assign_manifest_locators(conn, "doc1", ["fp-b"])
    assert a1.genesis_position == a0.genesis_position + 1

    repository.revoke_source_locator(conn, "doc1", a1.source_locator, "2024-06-01T00:00:00+00:00")

    [a2] = locator_manifest.assign_manifest_locators(conn, "doc1", ["fp-c"])
    assert a2.genesis_position > a1.genesis_position
    assert a2.source_locator != a1.source_locator


def test_unrelated_new_fragment_gets_the_next_strictly_higher_locator(conn):
    [a0] = locator_manifest.assign_manifest_locators(conn, "doc1", ["fp-a"])
    repository.revoke_source_locator(conn, "doc1", a0.source_locator, "2024-06-01T00:00:00+00:00")

    [a1] = locator_manifest.assign_manifest_locators(conn, "doc1", ["fp-unrelated"])
    assert a1.genesis_position > a0.genesis_position
    assert a1.source_locator != a0.source_locator


# ------------------------------------------------------------ natural locators


def test_revoked_natural_locator_raises_collision_error(conn):
    locator_manifest.assign_natural_locator(conn, "doc1", "t80", "fp-a")
    repository.revoke_source_locator(conn, "doc1", "t80", "2024-06-01T00:00:00+00:00")

    with pytest.raises(locator_manifest.RevokedLocatorCollisionError):
        locator_manifest.assign_natural_locator(conn, "doc1", "t80", "fp-new-content")


def test_live_natural_locator_continues_to_reuse_its_position(conn):
    first = locator_manifest.assign_natural_locator(conn, "doc1", "t80", "fp-a")
    second = locator_manifest.assign_natural_locator(conn, "doc1", "t80", "fp-a")
    assert second.genesis_position == first.genesis_position
    assert second.source_locator == "t80"
