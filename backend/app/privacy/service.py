"""Deletion / irreversible anonymization (CLAUDE.md 2.4, 18).

Flow (each stage is idempotent so a crash can resume from its recorded state):

    lock -> plan -> [manifest remap + atomic source replace]
         -> rebuild from the sanitized source (normal ingestion path)
         -> invalidate dependent Cases -> WAL checkpoint + VACUUM
         -> verify -> remove plan -> release lock

Redaction is applied to the app-owned canonical source (`data/source/`),
so a later rebuild cannot resurrect the person (18.3). Evidence IDs of
anonymized units are unchanged because the locator manifest's fingerprints
are remapped *before* the rebuild (18.8).

Known deviation from 18.6 step 4, disclosed rather than hidden: there is no
whole-unit deletion with locator revocation yet. A unit that redaction
empties is kept as a marker-only placeholder (the step-3 upper bound: the
whole text redacted), not removed.
"""

import json
import logging
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.core import anonymous_labels as labels
from app.core.enums import DocumentType
from app.db import migrations, repository
from app.ingestion import locator_manifest
from app.ingestion.embeddings import EmbeddingProvider, generate_embeddings
from app.ingestion.parsers import transcript as transcript_parser
from app.ingestion.service import _PARSERS, enumerate_source_files, ingest
from app.privacy import ops, redact, targets, verify
from app.privacy.ops import PrivacyOperationError

_LOGGER = logging.getLogger(__name__)
_MANIFEST_NAME = "reviewed_identities.json"
_STASH = "privacy_embedding_stash"


@dataclass
class PreviewResult:
    person_id: str
    author_units: int
    speaker_units: int
    mentioned_units: int
    units_to_anonymize: int
    files_to_sanitize: int
    cases_to_invalidate: int
    findings_to_invalidate: int = 0


@dataclass
class PurgeResult:
    operation_id: str
    files_sanitized: int
    units_anonymized: int
    cases_invalidated: int
    findings_invalidated: int
    embeddings_regenerated: int
    embeddings_pending: int
    verification: dict[str, int] = field(default_factory=dict)
    verified: bool = False


# --------------------------------------------------------------- preview


def preview(conn: sqlite3.Connection, source_dir: Path, person_id: str) -> PreviewResult | None:
    target = targets.resolve_target(conn, person_id)
    if target is None:
        return None
    summary = next(p for p in targets.list_people(conn) if p.person_id == person_id)
    files = _sanitize_all(source_dir, target)
    return PreviewResult(
        person_id=person_id,
        author_units=summary.author_units,
        speaker_units=summary.speaker_units,
        mentioned_units=summary.mentioned_units,
        units_to_anonymize=len(_affected_evidence_ids(conn, target)),
        files_to_sanitize=len(files),
        cases_to_invalidate=len(
            _dependent_case_ids(conn, target, _affected_evidence_ids(conn, target))
        ),
        findings_to_invalidate=len(
            _dependent_findings(
                conn,
                _affected_evidence_ids(conn, target),
                {"names": list(target.names), "emails": list(target.emails)},
            )
        ),
    )


# ----------------------------------------------------------------- purge


def purge(
    conn: sqlite3.Connection,
    *,
    source_dir: Path,
    db_path: Path,
    ops_dir: Path,
    person_id: str,
    artifact_dirs: list[Path] | None = None,
    provider: EmbeddingProvider | None = None,
) -> PurgeResult:
    """Run one full operation. Any failure leaves the lock in place and
    raises PrivacyOperationError; success is reported only after verification."""
    artifact_dirs = artifact_dirs or []
    ops.assert_unlocked(ops_dir)
    target = targets.resolve_target(conn, person_id)
    if target is None:
        raise PrivacyOperationError("person not found")

    op_id = uuid.uuid4().hex[:12]
    ops.acquire(ops_dir, op_id)  # from here on, a failure must leave the lock held
    try:
        migrations.initialize(conn)
        files = _sanitize_all(source_dir, target)
        affected = sorted(_affected_evidence_ids(conn, target))
        plan = {
            "op_id": op_id,
            "person_id": target.person_id,
            # Kept only so verification survives a crash (see module note); the
            # plan is deleted before the lock is released.
            "identifiers": {
                "canonical": target.canonical_name,
                "names": list(target.names),
                "emails": list(target.emails),
            },
            "files": files,
            "remap": _plan_manifest_remap(conn, source_dir, files),
            "affected_evidence_ids": affected,
            "had_embeddings": repository.embedding_row_count(conn) > 0,
        }
        ops.write_plan(ops_dir, plan)
        ops.set_state(ops_dir, ops.SOURCE_IN_PROGRESS)
        return _run(
            conn,
            plan,
            ops.SOURCE_IN_PROGRESS,
            source_dir,
            db_path,
            ops_dir,
            artifact_dirs,
            provider,
        )
    except PrivacyOperationError:
        raise
    except Exception as exc:
        _LOGGER.error("privacy operation failed op_id=%s error_type=%s", op_id, type(exc).__name__)
        raise PrivacyOperationError(
            "the privacy operation failed and the system remains locked for review"
        ) from None


def recover(
    *,
    source_dir: Path,
    db_path: Path,
    ops_dir: Path,
    artifact_dirs: list[Path] | None = None,
    provider: EmbeddingProvider | None = None,
) -> str:
    """Resolve an unfinished operation from its recorded state. Returns what
    was done; raises PrivacyOperationError (still locked) for anything that
    is not a recognised, safely resumable shape."""
    lock = ops.read_lock(ops_dir)
    if lock is None:
        return "no operation"
    state, plan = lock.get("state"), ops.read_plan(ops_dir)

    if state == ops.PLANNING and plan is None:
        # The plan is written before any source/database mutation begins, so a
        # PLANNING lock with no plan cannot have changed anything.
        ops.release(ops_dir)
        return "cleared orphan lock"
    if state == ops.FINALIZING and plan is None:
        report = _final_scan(ops_dir)
        if not report:
            raise PrivacyOperationError("final scan found staging leftovers; review needed")
        ops.release(ops_dir)
        return "finalized"
    if plan is None or state not in ops.STATES:
        raise PrivacyOperationError("unrecognised or unreadable operation state; review needed")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        _run(conn, plan, state, source_dir, db_path, ops_dir, artifact_dirs or [], provider)
    except PrivacyOperationError:
        raise
    except Exception as exc:
        _LOGGER.error("privacy recovery failed error_type=%s", type(exc).__name__)
        raise PrivacyOperationError("recovery failed; the system remains locked") from None
    finally:
        conn.close()
    return "resumed"


# ------------------------------------------------------------- the stages


def _run(conn, plan, state, source_dir, db_path, ops_dir, artifact_dirs, provider) -> PurgeResult:
    at = ops.STATES.index(state)
    regenerated = pending = 0
    invalidated = 0
    findings_invalidated = 0

    if at <= ops.STATES.index(ops.SOURCE_IN_PROGRESS):
        _apply_manifest_remap(conn, plan["remap"])
        for relative, text in plan["files"].items():
            ops.atomic_write(source_dir / relative, text)
        ops.set_state(ops_dir, ops.SOURCE_DONE)

    if at <= ops.STATES.index(ops.SOURCE_DONE):
        invalidated, findings_invalidated = _rebuild_from_sanitized_source(conn, plan, source_dir)
        ops.set_state(ops_dir, ops.DB_DONE)

    if at <= ops.STATES.index(ops.DB_DONE):
        _physical_cleanup(conn, db_path, artifact_dirs)
        ops.set_state(ops_dir, ops.CLEANUP_DONE)

    identifiers = plan["identifiers"]
    needle_list = verify.needles(
        identifiers["canonical"], identifiers["names"], identifiers["emails"]
    )
    if at <= ops.STATES.index(ops.CLEANUP_DONE):
        # Reopen so verification reads what is really on disk, not a cached page.
        fresh = sqlite3.connect(str(db_path))
        fresh.row_factory = sqlite3.Row
        try:
            report = verify.verify(
                conn=fresh,
                db_path=db_path,
                source_dir=source_dir,
                artifact_dirs=artifact_dirs,
                needle_list=needle_list,
                person_id=plan["person_id"],
            )
            stale = (
                fresh.execute(f"SELECT COUNT(*) FROM {_STASH}").fetchone()[0]
                if _table_exists(fresh, _STASH)
                else 0
            )
        finally:
            fresh.close()
        if not report.passed or stale:
            raise PrivacyOperationError("verification failed; the system remains locked")
        ops.set_state(ops_dir, ops.VERIFIED)
    else:
        report = verify.VerificationReport()

    # Embeddings for anonymized survivors are regenerated only now, while still
    # locked and never inside a database transaction (18.12).
    regenerated, pending = _regenerate_embeddings(conn, plan, provider)

    ops.set_state(ops_dir, ops.FINALIZING)
    ops.remove_plan(ops_dir)
    if not _final_scan(ops_dir):
        raise PrivacyOperationError("staging leftovers remain; the system remains locked")
    ops.release(ops_dir)

    return PurgeResult(
        operation_id=plan["op_id"],
        files_sanitized=len(plan["files"]),
        units_anonymized=len(plan["affected_evidence_ids"]),
        cases_invalidated=invalidated,
        findings_invalidated=findings_invalidated,
        embeddings_regenerated=regenerated,
        embeddings_pending=pending,
        verification=dict(report.counts),
        verified=True,
    )


def _rebuild_from_sanitized_source(conn, plan, source_dir: Path) -> tuple[int, int]:
    """Stash unchanged embeddings, rebuild through the normal ingestion path,
    restore them, and invalidate dependent Cases. Idempotent."""
    identifiers = plan["identifiers"]
    patterns = [targets.name_pattern(n) for n in identifiers["names"]]
    emails = [e.lower() for e in identifiers["emails"]]

    if not _table_exists(conn, _STASH):
        conn.execute(
            f"CREATE TABLE {_STASH} (evidence_id TEXT PRIMARY KEY, model_name TEXT NOT NULL, "
            "vector_json TEXT NOT NULL, text_hash TEXT NOT NULL)"
        )
        # Only units whose text mentions nobody being removed keep their vector:
        # an embedding of text containing the person must never survive.
        for row in conn.execute(
            "SELECT m.evidence_id, m.model_name, m.vector_json, e.raw_text, e.text_hash "
            "FROM evidence_embeddings m JOIN evidence_units e ON e.evidence_id = m.evidence_id"
        ).fetchall():
            text = row["raw_text"]
            if any(p.search(text) for p in patterns) or any(x in text.lower() for x in emails):
                continue
            conn.execute(
                f"INSERT OR IGNORE INTO {_STASH} VALUES (?, ?, ?, ?)",
                (row["evidence_id"], row["model_name"], row["vector_json"], row["text_hash"]),
            )
        conn.commit()

    ingest(conn, source_dir, embedding_provider=None)

    conn.execute(
        "INSERT OR IGNORE INTO evidence_embeddings (evidence_id, model_name, vector_json) "
        f"SELECT s.evidence_id, s.model_name, s.vector_json FROM {_STASH} s "
        "JOIN evidence_units e ON e.evidence_id = s.evidence_id AND e.text_hash = s.text_hash"
    )
    conn.execute(f"DROP TABLE {_STASH}")

    affected = set(plan["affected_evidence_ids"])
    # Findings first: removing one also removes the validated Case it links to.
    findings = _dependent_findings(conn, affected, identifiers)
    for finding_id in findings:
        _delete_finding(conn, finding_id)
    dependent = _dependent_case_ids_by(conn, affected, identifiers)
    for case_id in dependent:
        conn.execute("DELETE FROM case_evidence WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
    conn.commit()
    return len(dependent), len(findings)


def _physical_cleanup(conn, db_path: Path, artifact_dirs: list[Path]) -> None:
    """Flush old pages out of the database file, WAL and derived folders
    (18.4.1). Derived artifact/cache folders are disposable, so they are
    emptied rather than scrubbed."""
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for folder in artifact_dirs:
        if folder.exists():
            for child in folder.iterdir():
                shutil.rmtree(child) if child.is_dir() else child.unlink()


def _regenerate_embeddings(conn, plan, provider) -> tuple[int, int]:
    if not plan.get("had_embeddings"):
        return 0, 0
    rows = conn.execute(
        "SELECT e.evidence_id, e.raw_text FROM evidence_units e "
        "LEFT JOIN evidence_embeddings m ON m.evidence_id = e.evidence_id "
        "WHERE m.evidence_id IS NULL"
    ).fetchall()
    if not rows:
        return 0, 0
    if provider is None:
        return 0, len(rows)  # degraded: reported, never papered over
    report = generate_embeddings(conn, [(r["evidence_id"], r["raw_text"]) for r in rows], provider)
    conn.commit()
    return report.succeeded, len(rows) - report.succeeded


def _final_scan(ops_dir: Path) -> bool:
    """True when the operations folder holds nothing but the lock itself."""
    return all(p.name == ops.LOCK_NAME for p in ops_dir.iterdir()) if ops_dir.exists() else True


# --------------------------------------------------------------- planning


def _sanitize_all(source_dir: Path, target: targets.Target) -> dict[str, str]:
    """Relative path -> sanitized text, for every source file that changes."""
    changed: dict[str, str] = {}
    for path, kind in enumerate_source_files(source_dir):
        old = path.read_text(encoding="utf-8")
        new = redact.sanitize_text(old, kind, target)
        if new != old:
            changed[str(path.relative_to(source_dir))] = new
    manifest = source_dir / _MANIFEST_NAME
    if manifest.exists():
        text = manifest.read_text(encoding="utf-8")
        new = _sanitize_identity_manifest(text, target)
        if new != text:
            changed[_MANIFEST_NAME] = new
    return changed


def _sanitize_identity_manifest(text: str, target: targets.Target) -> str:
    """Remove the person's whole entry (18.1.1): every field of an entry is
    personal data, so deleting the person means deleting the entry."""
    data = json.loads(text)
    keep = []
    for entry in data.get("entries", []):
        name = str(entry.get("canonical_name", ""))
        aliases = [
            str(a.get("alias", a) if isinstance(a, dict) else a)
            for a in entry.get("verified_aliases", [])
        ]
        if any(targets.name_pattern(n).fullmatch(name) for n in target.names) or any(
            any(targets.name_pattern(n).fullmatch(a) for n in target.names) for a in aliases
        ):
            continue
        keep.append(entry)
    data["entries"] = keep
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _affected_evidence_ids(conn, target: targets.Target) -> set[str]:
    ids = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT evidence_id FROM evidence_people WHERE person_id = ?",
            (target.person_id,),
        )
    }
    patterns = [targets.name_pattern(n) for n in target.names]
    emails = [e.lower() for e in target.emails]
    for row in conn.execute(
        "SELECT evidence_id, raw_text, speaker_sender, thread_context FROM evidence_units"
    ):
        blob = " ".join(
            x or "" for x in (row["raw_text"], row["speaker_sender"], row["thread_context"])
        )
        if any(p.search(blob) for p in patterns) or any(x in blob.lower() for x in emails):
            ids.add(row["evidence_id"])
    return ids


def _dependent_case_ids(conn, target: targets.Target, affected: set[str]) -> set[str]:
    return _dependent_case_ids_by(
        conn, affected, {"names": list(target.names), "emails": list(target.emails)}
    )


def _dependent_case_ids_by(conn, affected: set[str], identifiers: dict) -> set[str]:
    cases: set[str] = set()
    if affected:
        marks = ",".join("?" * len(affected))
        cases.update(
            r[0]
            for r in conn.execute(
                f"SELECT DISTINCT case_id FROM case_evidence WHERE evidence_id IN ({marks})",
                sorted(affected),
            )
        )
    # Safety net: a Case whose stored prose names the person is derived personal
    # data even if it cites nothing that changed.
    patterns = [targets.name_pattern(n) for n in identifiers["names"]]
    emails = [e.lower() for e in identifiers["emails"]]
    for row in conn.execute("SELECT case_id, query, receipt_json FROM cases"):
        blob = f"{row['query']} {row['receipt_json']}"
        if any(p.search(blob) for p in patterns) or any(x in blob.lower() for x in emails):
            cases.add(row["case_id"])
    return cases


def _dependent_findings(conn, affected: set[str], identifiers: dict | None = None) -> set[str]:
    found: set[str] = set()
    if affected:
        marks = ",".join("?" * len(affected))
        found.update(
            r[0]
            for r in conn.execute(
                f"SELECT DISTINCT finding_id FROM finding_evidence WHERE evidence_id IN ({marks})",
                sorted(affected),
            )
        )
    if identifiers:
        # Safety net: a finding whose stored prose names the person is derived
        # personal data even if it cites nothing that changed.
        patterns = [targets.name_pattern(n) for n in identifiers["names"]]
        emails = [e.lower() for e in identifiers["emails"]]
        for row in conn.execute(
            "SELECT finding_id, title, summary, finding_json FROM pulse_findings"
        ):
            blob = f"{row['title']} {row['summary']} {row['finding_json']}"
            if any(p.search(blob) for p in patterns) or any(x in blob.lower() for x in emails):
                found.add(row["finding_id"])
    return found


def _delete_finding(conn, finding_id: str) -> None:
    """Remove a finding, its evidence links, and the validated Case it points at."""
    row = conn.execute(
        "SELECT finding_json FROM pulse_findings WHERE finding_id = ?", (finding_id,)
    ).fetchone()
    if row is not None:
        try:
            case_id = json.loads(row["finding_json"]).get("case_id")
        except ValueError:
            case_id = None
        if case_id:
            conn.execute("DELETE FROM case_evidence WHERE case_id = ?", (case_id,))
            conn.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
    conn.execute("DELETE FROM finding_evidence WHERE finding_id = ?", (finding_id,))
    conn.execute("DELETE FROM pulse_findings WHERE finding_id = ?", (finding_id,))


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


# ------------------------------------------------------- manifest remap


def _fingerprint_lists(kind: str, text: str, stem: str) -> list[tuple[str | None, str]]:
    """(natural_locator or None, fingerprint) for each fragment/unit, parsed
    with the same pure parser ingestion uses."""
    parse_fn, _doc_type = _PARSERS[kind]
    doc = parse_fn(text, stem, f"{stem}.txt")
    if doc.document_type == DocumentType.TRANSCRIPT.value:
        return [(f.natural_locator, repository.fingerprint(f.raw_text)) for f in doc.fragments]
    return [(u.natural_locator, repository.fingerprint(u.raw_text)) for u in doc.units]


def _plan_manifest_remap(conn, source_dir: Path, files: dict[str, str]) -> dict:
    """Old -> new fingerprint per changed fragment, resolved to locators, so
    the manifest can be updated before the rebuild and IDs stay stable.

    Only new fingerprints are put in the plan: persisting a prior content
    fingerprint would keep a value derived from the removed text (18.4.1).
    """
    remap: dict[str, list[list[str]]] = {}
    for relative, new_text in files.items():
        if relative == _MANIFEST_NAME:
            continue
        kind, filename = relative.split("/", 1)
        stem = Path(filename).stem
        old_text = (source_dir / relative).read_text(encoding="utf-8")
        if kind == "transcripts":
            # A database ingested before boundaries were persisted has none for
            # this document. Record them now, from the pre-redaction text, so
            # the rebuild cannot fuse adjacent redacted speakers.
            old_doc = _PARSERS[kind][0](old_text, stem, f"{stem}.txt")
            transcript_parser.assign_locators_and_merge(conn, stem, old_doc.fragments)
            conn.commit()
        old = _fingerprint_lists(kind, old_text, stem)
        new = _fingerprint_lists(kind, new_text, stem)
        if len(old) != len(new):
            # Redaction must never change how many units a document has here.
            raise PrivacyOperationError("sanitization changed a document's unit structure")

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


def _apply_manifest_remap(conn, remap: dict) -> None:
    for document_id, rows in remap.items():
        for locator, new_fp in rows:
            conn.execute(
                "UPDATE source_locators SET content_fingerprint = ? "
                "WHERE document_id = ? AND source_locator = ? AND revoked_at IS NULL",
                (new_fp, document_id, locator),
            )
    conn.commit()


_ = labels  # markers are written by redact.py; imported to keep the dependency explicit
