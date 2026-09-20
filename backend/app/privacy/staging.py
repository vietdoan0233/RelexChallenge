"""Staging helpers shared by both privacy-operation directions.

Split out from app/privacy/pseudonymise.py so that module and
app/privacy/reverse.py can both depend on this one without depending on
each other -- app/privacy/pseudonymise.py's recover() must be able to
dispatch to app/privacy/reverse.py's own resume logic by `op_kind`
(CLAUDE.md 18.10: crash recovery must resolve an unfinished operation from
its recorded state), which a direct import cycle would make impossible.

Everything here is identity-agnostic: it operates on already-computed
file-content diffs, fingerprints, and physical database/file cleanup, never
on a person's original name/email or which direction (pseudonymise/
reverse) produced the content it is given.
"""

import sqlite3
from pathlib import Path

from app.core.enums import DocumentType
from app.db import repository
from app.ingestion import locator_manifest
from app.ingestion.parsers import transcript as transcript_parser
from app.ingestion.service import _PARSERS
from app.privacy import ops
from app.privacy.ops import PrivacyOperationError

MANIFEST_NAME = "reviewed_identities.json"
EXTERNAL_SIGNALS_NAME = "external_signals.json"
STASH_TABLE = "privacy_embedding_stash"


def fingerprint_lists(kind: str, text: str, stem: str) -> list[tuple[str | None, str]]:
    """(natural_locator or None, fingerprint) for each fragment/unit, parsed
    with the same pure parser ingestion uses."""
    parse_fn, _doc_type = _PARSERS[kind]
    doc = parse_fn(text, stem, f"{stem}.txt")
    if doc.document_type == DocumentType.TRANSCRIPT.value:
        return [(f.natural_locator, repository.fingerprint(f.raw_text)) for f in doc.fragments]
    return [(u.natural_locator, repository.fingerprint(u.raw_text)) for u in doc.units]


def plan_manifest_remap(conn: sqlite3.Connection, source_dir: Path, files: dict[str, str]) -> dict:
    """Old -> new fingerprint per changed fragment, resolved to locators, so
    the manifest can be updated before the rebuild and IDs stay stable.

    Only new fingerprints are put in the plan: persisting a prior content
    fingerprint would keep a value derived from the rewritten text (18.4.1).
    `files` values are the *new* (already-computed) text -- this function
    never sees or stores original-identity-bearing content itself, only the
    fingerprints of what the caller already decided to write.
    """
    remap: dict[str, list[list[str]]] = {}
    for raw_relative, new_text in files.items():
        relative = raw_relative.replace("\\", "/")  # defensive: legacy Windows-separated plan
        if relative in (MANIFEST_NAME, EXTERNAL_SIGNALS_NAME):
            continue
        kind, filename = relative.split("/", 1)
        stem = Path(filename).stem
        old_text = (source_dir / relative).read_text(encoding="utf-8")
        if kind == "transcripts":
            # A database ingested before boundaries were persisted has none for
            # this document. Record them now, from the pre-rewrite text, so
            # the rebuild cannot fuse adjacent rewritten speakers.
            old_doc = _PARSERS[kind][0](old_text, stem, f"{stem}.txt")
            transcript_parser.assign_locators_and_merge(conn, stem, old_doc.fragments)
            conn.commit()
        old = fingerprint_lists(kind, old_text, stem)
        new = fingerprint_lists(kind, new_text, stem)
        if len(old) != len(new):
            # Rewriting must never change how many units a document has here.
            raise PrivacyOperationError("rewriting changed a document's unit structure")

        manifest_indices = [i for i, (loc, _fp) in enumerate(old) if loc is None]
        manifest_locators: dict[int, str] = {}
        if manifest_indices:
            before = len(repository.load_locator_manifest(conn, stem))
            assigned = locator_manifest.assign_manifest_locators(
                conn, stem, [old[i][1] for i in manifest_indices]
            )
            if len(repository.load_locator_manifest(conn, stem)) != before:
                conn.rollback()
                raise PrivacyOperationError("locator manifest out of sync with source")
            manifest_locators = {
                i: a.source_locator for i, a in zip(manifest_indices, assigned, strict=True)
            }
        rows = []
        for i, ((natural, old_fp), (_n2, new_fp)) in enumerate(zip(old, new, strict=True)):
            if old_fp == new_fp:
                continue
            locator = natural if natural is not None else manifest_locators[i]
            rows.append([locator, new_fp])
        if rows:
            remap[stem] = rows
    return remap


def apply_manifest_remap(conn: sqlite3.Connection, remap: dict) -> None:
    for document_id, rows in remap.items():
        for locator, new_fp in rows:
            conn.execute(
                "UPDATE source_locators SET content_fingerprint = ? "
                "WHERE document_id = ? AND source_locator = ? AND revoked_at IS NULL",
                (new_fp, document_id, locator),
            )
    conn.commit()


def write_files(source_dir: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        # Defensive: normalize a legacy plan that (pre-fix) may have
        # serialized a Windows-style path with backslashes.
        ops.atomic_write(source_dir / relative.replace("\\", "/"), text)


def physical_cleanup(conn: sqlite3.Connection, db_path: Path, artifact_dirs: list[Path]) -> None:
    """Flush old pages out of the database file, WAL and derived folders
    (18.4.1). Derived artifact/cache folders are disposable, so they are
    emptied rather than scrubbed."""
    import shutil

    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for folder in artifact_dirs:
        if folder.exists():
            for child in folder.iterdir():
                shutil.rmtree(child) if child.is_dir() else child.unlink()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def final_scan(ops_dir: Path) -> bool:
    """True when the operations folder holds nothing but the lock itself."""
    return all(p.name == ops.LOCK_NAME for p in ops_dir.iterdir()) if ops_dir.exists() else True
