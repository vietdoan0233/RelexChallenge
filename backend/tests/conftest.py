import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.db import migrations
from app.privacy.gate import gate


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    migrations.initialize(connection)
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def _reset_privacy_gate():
    """The reader/writer gate (app/privacy/gate.py) is one process-wide
    object; a test that fails partway through holding the write lease would
    otherwise wedge every later test in the same process."""
    yield
    gate.reset_for_tests()


@dataclass
class IsolatedInstance:
    """A temporary, on-disk instance -- source dir, database, artifacts
    dir, cache dir, and an encrypted reversal vault -- for tests that need
    real on-disk behavior (WAL/VACUUM, pseudonymisation, admin reversal)
    rather than the in-memory `conn` fixture used for pure logic tests. See
    CLAUDE.md/AGENTS.md section 0.5: any test that modifies source content,
    pseudonymises a subject, or simulates rebuild must use an instance
    shaped like this one and must never touch the repository's own
    data/source/, data/app.db, or data/private-vault/."""

    source_dir: Path
    db_path: Path
    artifacts_dir: Path
    cache_dir: Path
    ops_dir: Path
    vault_path: Path
    vault_key: str
    conn: sqlite3.Connection


@pytest.fixture
def isolated_instance(tmp_path):
    source_dir = tmp_path / "source"
    artifacts_dir = tmp_path / "artifacts"
    cache_dir = tmp_path / "cache"
    source_dir.mkdir()
    artifacts_dir.mkdir()
    cache_dir.mkdir()

    db_path = tmp_path / "app.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    migrations.initialize(connection)

    yield IsolatedInstance(
        source_dir=source_dir,
        db_path=db_path,
        artifacts_dir=artifacts_dir,
        cache_dir=cache_dir,
        ops_dir=tmp_path / "privacy_ops",
        vault_path=tmp_path / "private-vault" / "vault.db.enc",
        vault_key=Fernet.generate_key().decode(),
        conn=connection,
    )
    connection.close()


@pytest.fixture
def seed_units():
    """Insert a document and its evidence units (and matching FTS rows) into
    a test database. Returns the evidence ids in order. Used by the
    retrieval tests, which need small hand-built corpora with known
    rankings rather than the full archive."""
    from app.db import repository
    from app.schemas.evidence import Document, EvidenceUnit

    def _seed(
        conn,
        document_id,
        units,
        *,
        document_type="TRANSCRIPT",
        title=None,
        date="2025-01-01",
    ):
        repository.upsert_document(
            conn,
            Document(
                document_id=document_id,
                filename=f"{document_id}.txt",
                document_type=document_type,
                title=title or document_id,
                source_date=date,
                thread_context=title or document_id,
            ),
        )
        ids = []
        for index, unit in enumerate(units):
            text, speaker, event_date = (
                (unit, "Speaker", date) if isinstance(unit, str) else (unit + (date,))[:3]
            )
            evidence_id = f"EV-{document_id}-{index}"
            repository.insert_evidence_unit(
                conn,
                EvidenceUnit(
                    evidence_id=evidence_id,
                    document_id=document_id,
                    source_locator=str(index),
                    unit_index=index,
                    speaker_sender=speaker,
                    event_date=event_date,
                    thread_context=title or document_id,
                    raw_text=text,
                    text_hash=repository.fingerprint(text),
                ),
            )
            repository.insert_fts_row(
                conn, evidence_id, text, thread_context=title or document_id, speaker_sender=speaker
            )
            ids.append(evidence_id)
        conn.commit()
        return ids

    return _seed
