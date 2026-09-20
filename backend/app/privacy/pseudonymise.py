"""Robust pseudonymisation (AGENTS.md/CLAUDE.md 18.0, Architecture v1.6).

Superseded: app/privacy/service.py (retired v1.5 generic-marker deletion).
Nothing here calls that module or app/privacy/redact.py; both are removed.

Sequence (each stage idempotent so a crash can resume from recorded state):

    lock -> write-lease -> resolve ACTIVE subject -> vault write -> plan
         -> atomic source rewrite (alias-bearing)
         -> rebuild from the rewritten source (the normal ingestion path,
            now identity-stable: ingestion recognizes the subject's own
            display_alias in the rewritten text instead of minting a new
            person -- app/ingestion/people.py) + scrub original aliases
         -> invalidate dependent Cases/findings -> WAL checkpoint + VACUUM
         -> verify -> record PSEUDONYMISED + audit row -> remove plan
         -> release write-lease -> release lock

Evidence IDs of rewritten units are unchanged because the locator
manifest's fingerprints are remapped *before* the rebuild (CLAUDE.md 18.8);
Evidence Units, evidence_people relationships, and the participant row are
never deleted (CLAUDE.md 18.0.1).
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.db import migrations, repository
from app.ingestion.embeddings import EmbeddingProvider, generate_embeddings
from app.ingestion.service import enumerate_source_files, ingest
from app.privacy import ops, rewrite, staging, targets, vault, verify
from app.privacy.gate import gate
from app.privacy.ops import PrivacyOperationError
from app.privacy.staging import EXTERNAL_SIGNALS_NAME, MANIFEST_NAME, STASH_TABLE

_LOGGER = logging.getLogger(__name__)
OP_KIND = "pseudonymise"


@dataclass
class PreviewResult:
    subject_id: str
    display_alias: str
    author_units: int
    speaker_units: int
    mentioned_units: int
    units_to_rewrite: int
    files_to_rewrite: int
    cases_to_invalidate: int
    findings_to_invalidate: int = 0
    # Strict first-name basis (app/ingestion/name_resolution.py): the bare first name that
    # will be rewritten along with the full name, and -- if the person has a first name that
    # was NOT safe to assign -- which one and why (shared | ordinary-word | too-short | reserved).
    first_name: str | None = None
    unassigned_first_name: str | None = None
    unassigned_reason: str | None = None


@dataclass
class PseudonymisationResult:
    operation_id: str
    subject_id: str
    display_alias: str
    privacy_state: str
    files_rewritten: int
    units_rewritten: int
    cases_invalidated: int
    findings_invalidated: int
    embeddings_regenerated: int
    embeddings_pending: int
    verification: dict[str, int] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)
    verified: bool = False
    pseudonymised_at: str | None = None


# --------------------------------------------------------------- preview


def preview(conn: sqlite3.Connection, source_dir: Path, subject_id: str) -> PreviewResult | None:
    target = targets.resolve_active_target(conn, subject_id)
    if target is None:
        return None
    summary = next(p for p in targets.list_people(conn) if p.subject_id == subject_id)
    files = _rewrite_all(source_dir, target)
    affected = _affected_evidence_ids(conn, target)
    identifiers = {"names": list(target.names), "emails": list(target.emails)}
    return PreviewResult(
        subject_id=subject_id,
        display_alias=target.display_alias,
        author_units=summary.author_units,
        speaker_units=summary.speaker_units,
        mentioned_units=summary.mentioned_units,
        units_to_rewrite=len(affected),
        files_to_rewrite=len(files),
        cases_to_invalidate=len(_dependent_case_ids_by(conn, affected, identifiers)),
        findings_to_invalidate=len(_dependent_findings(conn, affected, identifiers)),
        first_name=target.first_name,
        unassigned_first_name=target.unassigned_first_name,
        unassigned_reason=target.unassigned_reason,
    )


# ---------------------------------------------------------- pseudonymise


def pseudonymise(
    conn: sqlite3.Connection,
    *,
    source_dir: Path,
    db_path: Path,
    ops_dir: Path,
    vault_path: Path,
    vault_key: str,
    subject_id: str,
    artifact_dirs: list[Path] | None = None,
    provider: EmbeddingProvider | None = None,
) -> PseudonymisationResult:
    """Run one full operation. Any failure leaves the lock in place and
    raises PrivacyOperationError; success is reported only after verification."""
    artifact_dirs = artifact_dirs or []
    ops.assert_unlocked(ops_dir)
    target = targets.resolve_active_target(conn, subject_id)
    if target is None:
        raise PrivacyOperationError("subject not found, or not currently ACTIVE")

    op_id = uuid.uuid4().hex[:12]
    ops.acquire(ops_dir, op_id)  # from here on, a failure must leave the lock held
    try:
        with gate.write_lease():
            migrations.initialize(conn)

            bundle = vault.IdentityBundle(
                original_name=target.display_name,
                original_emails=target.emails,
                original_aliases=tuple(n for n in target.names if n != target.display_name),
            )
            vault.store_identity(vault_path, vault_key, subject_id, bundle)

            files = _rewrite_all(source_dir, target)
            affected = sorted(_affected_evidence_ids(conn, target))
            pre_relationships = sorted(
                [row["evidence_id"], row["subject_id"], row["relation"]]
                for row in conn.execute(
                    "SELECT evidence_id, subject_id, relation FROM evidence_people "
                    "WHERE subject_id = ?",
                    (subject_id,),
                )
            )
            plan = {
                "op_kind": OP_KIND,
                "op_id": op_id,
                "subject_id": subject_id,
                "display_alias": target.display_alias,
                # No original name/email/alias below -- only IDs, paths,
                # already-alias-bearing replacement text, and counts
                # (CLAUDE.md 18.0.5). The original identity for
                # crash-recovery verification comes back from the vault
                # entry written just above, never from this file.
                "files": files,
                "remap": staging.plan_manifest_remap(conn, source_dir, files),
                "affected_evidence_ids": affected,
                "pre_relationships": pre_relationships,
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
                vault_path,
                vault_key,
                artifact_dirs,
                provider,
            )
    except PrivacyOperationError:
        raise
    except Exception as exc:
        _LOGGER.error("pseudonymisation failed op_id=%s error_type=%s", op_id, type(exc).__name__)
        raise PrivacyOperationError(
            "the pseudonymisation operation failed and the system remains locked for review"
        ) from None


def recover(
    *,
    source_dir: Path,
    db_path: Path,
    ops_dir: Path,
    vault_path: Path,
    vault_key: str,
    artifact_dirs: list[Path] | None = None,
    provider: EmbeddingProvider | None = None,
) -> str:
    """Resolve an unfinished privacy operation from its recorded state, of
    *either* direction. Returns what was done; raises PrivacyOperationError
    (still locked) for anything that is not a recognised, safely resumable
    shape.

    This is the single recovery entry point app/main.py calls at startup
    (CLAUDE.md 18.10), so it must be able to tell a forward-pseudonymisation
    plan from a reversal plan apart -- an interrupted reversal resumed as if
    it were a forward operation (or vice versa) would misread its own state
    and could corrupt or mis-verify it. `op_kind` (written into the plan by
    whichever direction started it) makes that dispatch explicit rather
    than guessed. A plan predating this field (should not exist outside a
    stale dev database) is treated as a forward-pseudonymisation plan for
    backward compatibility, matching this module's own historical shape.
    """
    lock = ops.read_lock(ops_dir)
    if lock is None:
        return "no operation"
    state, plan = lock.get("state"), ops.read_plan(ops_dir)

    if state == ops.PLANNING and plan is None:
        ops.release(ops_dir)
        return "cleared orphan lock"
    if state == ops.FINALIZING and plan is None:
        # The plan (and therefore op_kind) is already gone; the final scan
        # is direction-agnostic, so no dispatch is needed here.
        if not staging.final_scan(ops_dir):
            raise PrivacyOperationError("final scan found staging leftovers; review needed")
        ops.release(ops_dir)
        return "finalized"
    if plan is None or state not in ops.STATES:
        raise PrivacyOperationError("unrecognised or unreadable operation state; review needed")

    if plan.get("op_kind") == "reverse":
        from app.privacy import reverse

        return reverse.recover(
            source_dir=source_dir,
            db_path=db_path,
            ops_dir=ops_dir,
            vault_path=vault_path,
            vault_key=vault_key,
            artifact_dirs=artifact_dirs,
            provider=provider,
            lock_state=state,
            plan=plan,
        )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        with gate.write_lease():
            _run(
                conn,
                plan,
                state,
                source_dir,
                db_path,
                ops_dir,
                vault_path,
                vault_key,
                artifact_dirs or [],
                provider,
            )
    except PrivacyOperationError:
        raise
    except Exception as exc:
        _LOGGER.error("pseudonymisation recovery failed error_type=%s", type(exc).__name__)
        raise PrivacyOperationError("recovery failed; the system remains locked") from None
    finally:
        conn.close()
    return "resumed"


# ------------------------------------------------------------- the stages


def _run(
    conn,
    plan,
    state,
    source_dir,
    db_path,
    ops_dir,
    vault_path,
    vault_key,
    artifact_dirs,
    provider,
) -> PseudonymisationResult:
    at = ops.STATES.index(state)
    subject_id = plan["subject_id"]
    invalidated = findings_invalidated = 0

    # The vault entry is written before the plan (see pseudonymise() above),
    # so it is always available here, including on crash recovery in a
    # fresh process that never held `target` in memory. This is the one
    # narrow, internal exception to "only the admin reversal workflow
    # decrypts the vault": it is the same already-authorized operation
    # reading back the bundle *it* just wrote, purely to rebuild the
    # verification needle list, and the plaintext never leaves this
    # function -- it is not returned, logged, or written to the plan.
    bundle = vault.retrieve_identity(vault_path, vault_key, subject_id)
    if bundle is None:
        raise PrivacyOperationError("vault record missing for this operation; cannot proceed")
    identifier_names = [bundle.original_name, *bundle.original_aliases]
    identifier_emails = list(bundle.original_emails)
    needle_list = verify.needles(
        bundle.original_name, list(bundle.original_aliases), identifier_emails
    )

    if at <= ops.STATES.index(ops.SOURCE_IN_PROGRESS):
        staging.apply_manifest_remap(conn, plan["remap"])
        staging.write_files(source_dir, plan["files"])
        ops.set_state(ops_dir, ops.SOURCE_DONE)

    if at <= ops.STATES.index(ops.SOURCE_DONE):
        invalidated, findings_invalidated = _rebuild_from_rewritten_source(
            conn, plan, source_dir, identifier_names, identifier_emails
        )
        ops.set_state(ops_dir, ops.DB_DONE)

    if at <= ops.STATES.index(ops.DB_DONE):
        staging.physical_cleanup(conn, db_path, artifact_dirs)
        ops.set_state(ops_dir, ops.CLEANUP_DONE)

    if at <= ops.STATES.index(ops.CLEANUP_DONE):
        # Reopen so verification reads what is really on disk, not a cached page.
        fresh = sqlite3.connect(str(db_path))
        fresh.row_factory = sqlite3.Row
        try:
            report = verify.verify(
                conn=fresh,
                db_path=db_path,
                source_dir=source_dir,
                vault_path=vault_path,
                artifact_dirs=artifact_dirs,
                needle_list=needle_list,
                subject_id=subject_id,
                display_alias=plan["display_alias"],
                pre_operation_evidence_people={tuple(x) for x in plan["pre_relationships"]},
            )
            stale = (
                fresh.execute(f"SELECT COUNT(*) FROM {STASH_TABLE}").fetchone()[0]
                if staging.table_exists(fresh, STASH_TABLE)
                else 0
            )
        finally:
            fresh.close()
        # This is the hard privacy gate: identifiers absent, relationships
        # preserved, state correct. It must never depend on embeddings --
        # a missing/unreachable embedding provider must not leave the
        # system permanently locked (18.12).
        if not report.passed or stale:
            raise PrivacyOperationError("verification failed; the system remains locked")
        ops.set_state(ops_dir, ops.VERIFIED)

        # Embeddings for rewritten survivors are regenerated only now, while
        # still locked and never inside a database transaction (18.12) --
        # but a pending regeneration must not be *hidden* by an otherwise-
        # green "verified" label: the audit record and the returned result
        # both fold embeddings completeness into `checks`/`verified` below,
        # without this ever raising or blocking release of the lock.
        regenerated, pending = _regenerate_embeddings(conn, plan, provider)

        pseudonymised_at = conn.execute(
            "SELECT pseudonymised_at FROM people WHERE subject_id = ?", (subject_id,)
        ).fetchone()["pseudonymised_at"]
        # Mutated in place (not a copy) so report.passed/report.checks, used
        # below to compute the returned `checks` and `verified` fields, see
        # this too.
        report.checks["no_embeddings_pending_for_changed_evidence"] = pending == 0
        verification_json = json.dumps({"counts": report.counts, "checks": report.checks})
        conn.execute(
            "UPDATE people SET verification_result_json = ? WHERE subject_id = ?",
            (verification_json, subject_id),
        )
        conn.execute(
            "INSERT INTO privacy_operations (operation_id, subject_id, from_state, to_state, "
            "display_alias, pseudonymised_at, verification_result_json, created_at) "
            "VALUES (?, ?, 'ACTIVE', 'PSEUDONYMISED', ?, ?, ?, ?)",
            (
                plan["op_id"],
                subject_id,
                plan["display_alias"],
                pseudonymised_at,
                verification_json,
                pseudonymised_at,
            ),
        )
        conn.commit()
    else:
        # Resuming from VERIFIED or FINALIZING: the hard gate already passed
        # in an earlier run. Re-attempt embeddings (idempotent -- it only
        # ever targets evidence still missing a row) and read back the
        # persisted counts/checks/timestamp rather than recomputing them.
        regenerated, pending = _regenerate_embeddings(conn, plan, provider)
        row = conn.execute(
            "SELECT pseudonymised_at, verification_result_json FROM people WHERE subject_id = ?",
            (subject_id,),
        ).fetchone()
        pseudonymised_at = row["pseudonymised_at"] if row else None
        stored = (
            json.loads(row["verification_result_json"])
            if row and row["verification_result_json"]
            else {}
        )
        report = verify.VerificationReport(
            counts=stored.get("counts", {}), checks=stored.get("checks", {})
        )
        embeddings_check = "no_embeddings_pending_for_changed_evidence"
        if pending == 0 and not report.checks.get(embeddings_check, True):
            # Embeddings finished catching up since the last persisted record
            # (e.g. a provider that was down is back); refresh the stored flag
            # so the audit record does not understate a now-complete state.
            report.checks[embeddings_check] = True
            verification_json = json.dumps({"counts": report.counts, "checks": report.checks})
            conn.execute(
                "UPDATE people SET verification_result_json = ? WHERE subject_id = ?",
                (verification_json, subject_id),
            )
            conn.commit()

    ops.set_state(ops_dir, ops.FINALIZING)
    ops.remove_plan(ops_dir)
    if not staging.final_scan(ops_dir):
        raise PrivacyOperationError("staging leftovers remain; the system remains locked")
    ops.release(ops_dir)

    # `verified` reflects the *complete* picture, not just the hard privacy
    # gate: a pseudonymisation with identifiers correctly removed but
    # embeddings still pending for changed evidence is not fully verified
    # yet, even though it is not an error and the system is not locked.
    fully_verified = report.passed and pending == 0

    return PseudonymisationResult(
        operation_id=plan["op_id"],
        subject_id=subject_id,
        display_alias=plan["display_alias"],
        privacy_state="PSEUDONYMISED",
        files_rewritten=len(plan["files"]),
        units_rewritten=len(plan["affected_evidence_ids"]),
        cases_invalidated=invalidated,
        findings_invalidated=findings_invalidated,
        embeddings_regenerated=regenerated,
        embeddings_pending=pending,
        verification=dict(report.counts),
        checks=dict(report.checks),
        verified=fully_verified,
        pseudonymised_at=pseudonymised_at,
    )


def _rebuild_from_rewritten_source(
    conn, plan, source_dir: Path, identifier_names: list[str], identifier_emails: list[str]
) -> tuple[int, int]:
    """Stash unchanged embeddings, rebuild through the normal ingestion
    path, restore them, scrub the subject's now-obsolete original aliases,
    record the PSEUDONYMISED state, and invalidate dependent Cases.
    Idempotent."""
    subject_id = plan["subject_id"]
    patterns = [targets.name_pattern(n) for n in identifier_names]
    emails = [e.lower() for e in identifier_emails]

    if not staging.table_exists(conn, STASH_TABLE):
        conn.execute(
            f"CREATE TABLE {STASH_TABLE} (evidence_id TEXT PRIMARY KEY, model_name TEXT NOT NULL, "
            "vector_json TEXT NOT NULL, text_hash TEXT NOT NULL)"
        )
        # Only units whose text mentions nobody being rewritten keep their
        # vector: an embedding of text containing the original identity
        # must never survive.
        for row in conn.execute(
            "SELECT m.evidence_id, m.model_name, m.vector_json, e.raw_text, e.text_hash "
            "FROM evidence_embeddings m JOIN evidence_units e ON e.evidence_id = m.evidence_id"
        ).fetchall():
            text = row["raw_text"]
            if any(p.search(text) for p in patterns) or any(x in text.lower() for x in emails):
                continue
            conn.execute(
                f"INSERT OR IGNORE INTO {STASH_TABLE} VALUES (?, ?, ?, ?)",
                (row["evidence_id"], row["model_name"], row["vector_json"], row["text_hash"]),
            )
        conn.commit()

    ingest(conn, source_dir, embedding_provider=None)

    conn.execute(
        "INSERT OR IGNORE INTO evidence_embeddings (evidence_id, model_name, vector_json) "
        f"SELECT s.evidence_id, s.model_name, s.vector_json FROM {STASH_TABLE} s "
        "JOIN evidence_units e ON e.evidence_id = s.evidence_id AND e.text_hash = s.text_hash"
    )
    conn.execute(f"DROP TABLE {STASH_TABLE}")

    # The rebuild re-links evidence_people for this subject via their now
    # alias-bearing source text (app/ingestion/people.py); only now do we
    # scrub the original identity from the public alias table and flip the
    # public state -- after the rebuild, so ingestion still had the
    # original FULL_NAME/EMAIL aliases available to resolve *other* units
    # that had not yet been rewritten in earlier resumed states.
    conn.execute("DELETE FROM person_aliases WHERE subject_id = ?", (subject_id,))
    conn.execute(
        "UPDATE people SET privacy_state = 'PSEUDONYMISED', display_name = NULL, "
        "profile_metadata_json = NULL, pseudonymisation_operation_id = ?, "
        "pseudonymised_at = COALESCE(pseudonymised_at, ?) "
        "WHERE subject_id = ?",
        (plan["op_id"], datetime.now(UTC).isoformat(), subject_id),
    )

    identifiers = {"names": identifier_names, "emails": identifier_emails}
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


# --------------------------------------------------------------- planning


def _rewrite_all(source_dir: Path, target: targets.Target) -> dict[str, str]:
    """Relative path -> rewritten text, for every source file that changes.

    Covers every application-owned surface under data/source/ that can
    identify a participant, not only the evidence documents: the reviewed
    identity manifest, and external_signals.json, whose own file
    description requires it be "scanned like any other application-owned
    surface" -- so it must also be *rewritten* like one, not merely
    verified clean by happening not to match (AGENTS.md 18.0.4's "other
    direct identifying metadata").

    Keys are always POSIX-separated (`.as_posix()`), never `str(Path(...))`,
    because the latter renders backslashes on Windows -- and every reader of
    this dict (`staging.plan_manifest_remap`'s `relative.split("/", 1)`, and
    the atomic-write loop in `_run`) parses on a literal "/". A plan written
    with native Windows separators would silently fail to split into
    (kind, filename) and would still *write* to the right place via
    `source_dir / relative` (pathlib accepts "/" on every platform), but
    would break every path-shaped lookup that assumes "/". See AGENTS.md's
    "Windows privacy-plan separator bug" note.
    """
    changed: dict[str, str] = {}
    for path, kind in enumerate_source_files(source_dir):
        old = path.read_text(encoding="utf-8")
        new = rewrite.rewrite_text(old, kind, target)
        if new != old:
            changed[path.relative_to(source_dir).as_posix()] = new
    manifest = source_dir / MANIFEST_NAME
    if manifest.exists():
        text = manifest.read_text(encoding="utf-8")
        new = _rewrite_identity_manifest(text, target)
        if new != text:
            changed[MANIFEST_NAME] = new
    signals = source_dir / EXTERNAL_SIGNALS_NAME
    if signals.exists():
        text = signals.read_text(encoding="utf-8")
        new = rewrite.rewrite_plain_text(text, target)
        if new != text:
            changed[EXTERNAL_SIGNALS_NAME] = new
    return changed


def _rewrite_identity_manifest(text: str, target: targets.Target) -> str:
    """Remove the subject's whole entry: their identity is now fully
    represented by one stable alias with nothing left to promote, and every
    field of an existing entry (short-form aliases, review notes) is
    original-identity-bearing text that must not survive under the new
    canonical name."""
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
            "SELECT DISTINCT evidence_id FROM evidence_people WHERE subject_id = ?",
            (target.subject_id,),
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
    # Safety net: a Case whose stored prose names the person is derived
    # personal data even if it cites nothing that changed.
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


# Fingerprint remapping, physical cleanup, and other identity-agnostic
# staging helpers live in app/privacy/staging.py, shared with
# app/privacy/reverse.py (see that module's docstring for why: avoiding an
# import cycle so pseudonymise.recover() can dispatch to reverse.recover()).
