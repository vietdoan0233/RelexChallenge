"""Explicit admin reversal workflow (AGENTS.md/CLAUDE.md 18.0.7).

Not exposed through any standard profile/search/evidence API, and never
available merely because a caller knows a subject_id or display_alias --
app/api/admin.py gates this behind the same admin-token dependency as
pseudonymisation, plus an explicit `confirm: true` in the request body
(mirroring the same requirement on POST /api/privacy/pseudonymise). This
is the one workflow, alongside app/privacy/pseudonymise.py's own
crash-recovery path, that decrypts the vault.

Staged and crash-resumable, mirroring app/privacy/pseudonymise.py's state
machine (PLANNING -> SOURCE_IN_PROGRESS -> SOURCE_DONE -> DB_DONE ->
CLEANUP_DONE -> VERIFIED -> FINALIZING) via the shared app/privacy/ops.py
lock/plan infrastructure and app/privacy/staging.py helpers, and dispatched
to from app/privacy/pseudonymise.recover() by this plan's `op_kind` so a
crash mid-reversal is resumed as a reversal, never misread as a forward
pseudonymisation resuming (or vice versa).

Security-critical: unlike forward pseudonymisation's plan (which may hold
already-alias-bearing replacement text, since an alias is not sensitive),
this module's plan NEVER contains the restored original name/email or any
restored file content. The plan holds only op_kind/op_id/subject_id/
display_alias/pre_relationships -- all non-sensitive IDs and counts. The
actual restore text is recomputed fresh from the vault at the start of
every stage that needs it (whether this is the first attempt or a resumed
one after a crash) and lives only in local variables for the few lines it
takes to write it straight to the canonical source; it is never returned,
logged, or persisted anywhere outside data/source/ itself and the vault.
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.core.enums import AliasType
from app.db import repository
from app.ingestion.embeddings import EmbeddingProvider, generate_embeddings
from app.ingestion.service import enumerate_source_files, ingest
from app.privacy import ops, rewrite, staging, verify
from app.privacy.gate import gate
from app.privacy.ops import PrivacyOperationError
from app.privacy.staging import EXTERNAL_SIGNALS_NAME, STASH_TABLE
from app.privacy.vault import IdentityBundle, VaultError, retrieve_identity

_LOGGER = logging.getLogger(__name__)
OP_KIND = "reverse"


@dataclass
class ReversalResult:
    operation_id: str
    subject_id: str
    display_alias: str
    privacy_state: str
    files_restored: int
    embeddings_regenerated: int = 0
    embeddings_pending: int = 0
    verified: bool = False
    verification: dict[str, int] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)


def _load_bundle(vault_path: Path, vault_key: str, subject_id: str) -> IdentityBundle:
    try:
        bundle = retrieve_identity(vault_path, vault_key, subject_id)
    except VaultError:
        raise PrivacyOperationError("vault record could not be decrypted") from None
    if bundle is None:
        raise PrivacyOperationError("no vault record exists for this subject")
    return bundle


# ------------------------------------------------------------- entry points


def reverse_pseudonymisation(
    conn: sqlite3.Connection,
    *,
    source_dir: Path,
    db_path: Path,
    ops_dir: Path,
    vault_path: Path,
    vault_key: str,
    subject_id: str,
    confirm: bool = False,
    artifact_dirs: list[Path] | None = None,
    provider: EmbeddingProvider | None = None,
) -> ReversalResult:
    if not confirm:
        # Fails before touching any lock/vault/source state -- an
        # unconfirmed call has zero side effects, matching the same
        # explicit-confirmation requirement on POST /api/privacy/pseudonymise.
        raise PrivacyOperationError("confirm=true is required to reverse pseudonymisation")
    artifact_dirs = artifact_dirs or []
    ops.assert_unlocked(ops_dir)

    person = repository.get_person(conn, subject_id)
    if person is None or person["privacy_state"] != "PSEUDONYMISED":
        raise PrivacyOperationError("subject not found, or not currently PSEUDONYMISED")
    display_alias = person["display_alias"]

    # Confirm a vault record exists before locking anything; this call's
    # result is discarded immediately -- it exists only to fail early and
    # cleanly, exactly like an unknown subject_id, not to hold plaintext.
    _load_bundle(vault_path, vault_key, subject_id)

    pre_relationships = sorted(
        [row["evidence_id"], row["subject_id"], row["relation"]]
        for row in conn.execute(
            "SELECT evidence_id, subject_id, relation FROM evidence_people WHERE subject_id = ?",
            (subject_id,),
        )
    )

    op_id = uuid.uuid4().hex[:12]
    ops.acquire(ops_dir, op_id)  # from here on, a failure must leave the lock held
    try:
        with gate.write_lease():
            plan = {
                "op_kind": OP_KIND,
                "op_id": op_id,
                "subject_id": subject_id,
                "display_alias": display_alias,
                "pre_relationships": pre_relationships,
                # Deliberately nothing else: no original name/email/alias,
                # no restored file content. See module docstring.
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
        _LOGGER.error("reversal failed op_id=%s error_type=%s", op_id, type(exc).__name__)
        raise PrivacyOperationError(
            "the reversal operation failed and the system remains locked for review"
        ) from None


def recover(
    *,
    source_dir: Path,
    db_path: Path,
    ops_dir: Path,
    vault_path: Path,
    vault_key: str,
    artifact_dirs: list[Path] | None,
    provider: EmbeddingProvider | None,
    lock_state: str,
    plan: dict,
) -> str:
    """Called only by app/privacy/pseudonymise.recover()'s dispatcher, which
    has already read the lock/plan file and confirmed
    `plan["op_kind"] == "reverse"` -- there is exactly one place in the
    codebase that interprets a raw lock/plan file at startup, so this does
    not re-read them itself."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        with gate.write_lease():
            _run(
                conn,
                plan,
                lock_state,
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
        _LOGGER.error("reversal recovery failed error_type=%s", type(exc).__name__)
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
) -> ReversalResult:
    at = ops.STATES.index(state)
    subject_id = plan["subject_id"]
    display_alias = plan["display_alias"]

    if at <= ops.STATES.index(ops.SOURCE_IN_PROGRESS):
        bundle = _load_bundle(vault_path, vault_key, subject_id)
        original_email = bundle.original_emails[0] if bundle.original_emails else None
        files = _restore_all(source_dir, display_alias, bundle.original_name, original_email)
        remap = staging.plan_manifest_remap(conn, source_dir, files)
        # Write the source before committing the manifest fingerprint remap
        # (CLAUDE.md 18.10 step order: source is replaced, *then* the
        # logical DB change is committed). Unlike app/privacy/pseudonymise.py
        # -- which persists a fixed `files`/`remap` in the plan and can
        # safely replay the same values on resume regardless of order --
        # this module recomputes both fresh from current disk content on
        # every call (by design: the plan must never hold restored original
        # text). Committing the fingerprint remap first would leave the
        # manifest referencing the *new* fingerprint while disk still held
        # the *old* text if a crash landed between the two steps; a resumed
        # recompute would then see old disk content whose fingerprint no
        # longer matches the manifest and fail as "out of sync". Writing
        # first means a crash before the write leaves both disk and
        # manifest untouched, so a retry recomputes and applies cleanly.
        staging.write_files(source_dir, files)
        staging.apply_manifest_remap(conn, remap)
        # `bundle`/`files`/`original_email` go out of scope here and are
        # never written to the plan: only their *count* is safe to persist.
        plan["files_restored_count"] = len(files)
        ops.write_plan(ops_dir, plan)
        ops.set_state(ops_dir, ops.SOURCE_DONE)

    if at <= ops.STATES.index(ops.SOURCE_DONE):
        bundle = _load_bundle(vault_path, vault_key, subject_id)
        # Stash every embedding whose text does NOT mention the alias (i.e.
        # is unaffected by this restore) *before* ingest() overwrites
        # raw_text, mirroring app/privacy/pseudonymise.py's own stash
        # pattern. An embedding for alias-bearing text must never survive
        # the restore (18.12): by only stashing the unaffected ones and
        # restoring stashed rows keyed on text_hash after rebuild, any
        # affected evidence_id simply comes back with no embedding row,
        # so it is correctly reported pending rather than silently stale.
        if not staging.table_exists(conn, STASH_TABLE):
            conn.execute(
                f"CREATE TABLE {STASH_TABLE} (evidence_id TEXT PRIMARY KEY, "
                "model_name TEXT NOT NULL, vector_json TEXT NOT NULL, text_hash TEXT NOT NULL)"
            )
            for row in conn.execute(
                "SELECT m.evidence_id, m.model_name, m.vector_json, e.raw_text, e.text_hash "
                "FROM evidence_embeddings m JOIN evidence_units e ON e.evidence_id = m.evidence_id"
            ).fetchall():
                if display_alias in (row["raw_text"] or ""):
                    continue
                conn.execute(
                    f"INSERT OR IGNORE INTO {STASH_TABLE} VALUES (?, ?, ?, ?)",
                    (row["evidence_id"], row["model_name"], row["vector_json"], row["text_hash"]),
                )
            conn.commit()
        _restore_identity_row(conn, subject_id, bundle)
        ingest(conn, source_dir, embedding_provider=None)
        conn.execute(
            "INSERT OR IGNORE INTO evidence_embeddings (evidence_id, model_name, vector_json) "
            f"SELECT s.evidence_id, s.model_name, s.vector_json FROM {STASH_TABLE} s "
            "JOIN evidence_units e ON e.evidence_id = s.evidence_id AND e.text_hash = s.text_hash"
        )
        conn.execute(f"DROP TABLE {STASH_TABLE}")
        _invalidate_alias_dependents(conn, display_alias)
        conn.commit()
        ops.set_state(ops_dir, ops.DB_DONE)

    if at <= ops.STATES.index(ops.DB_DONE):
        staging.physical_cleanup(conn, db_path, artifact_dirs)
        ops.set_state(ops_dir, ops.CLEANUP_DONE)

    if at <= ops.STATES.index(ops.CLEANUP_DONE):
        fresh = sqlite3.connect(str(db_path))
        fresh.row_factory = sqlite3.Row
        try:
            counts, checks = _verify(
                fresh, source_dir, artifact_dirs, subject_id, display_alias, plan
            )
            stale = (
                fresh.execute(f"SELECT COUNT(*) FROM {STASH_TABLE}").fetchone()[0]
                if staging.table_exists(fresh, STASH_TABLE)
                else 0
            )
        finally:
            fresh.close()
        # Hard gate: alias absent from content, active identity restored,
        # relationships preserved. Must never depend on embeddings (18.12).
        if not all(v == 0 for v in counts.values()) or not all(checks.values()) or stale:
            raise PrivacyOperationError(
                "reversal verification failed; the system remains locked for review"
            )
        ops.set_state(ops_dir, ops.VERIFIED)

        regenerated, pending = _regenerate_stale_embeddings(conn, provider)
        checks["no_embeddings_pending_for_changed_evidence"] = pending == 0
        reversed_at = datetime.now(UTC).isoformat()
        audit_json = json.dumps({"counts": counts, "checks": checks})
        conn.execute(
            "INSERT INTO privacy_operations (operation_id, subject_id, from_state, to_state, "
            "display_alias, pseudonymised_at, verification_result_json, created_at) "
            "VALUES (?, ?, 'PSEUDONYMISED', 'ACTIVE', ?, NULL, ?, ?)",
            (plan["op_id"], subject_id, display_alias, audit_json, reversed_at),
        )
        conn.commit()
    else:
        # Resuming from VERIFIED or FINALIZING: the hard gate already
        # passed. Re-attempt embeddings (idempotent) and read back the
        # persisted audit record rather than recomputing it.
        regenerated, pending = _regenerate_stale_embeddings(conn, provider)
        row = conn.execute(
            "SELECT verification_result_json FROM privacy_operations WHERE operation_id = ?",
            (plan["op_id"],),
        ).fetchone()
        stored = (
            json.loads(row["verification_result_json"])
            if row and row["verification_result_json"]
            else {}
        )
        counts, checks = stored.get("counts", {}), dict(stored.get("checks", {}))
        if pending == 0:
            checks["no_embeddings_pending_for_changed_evidence"] = True

    ops.set_state(ops_dir, ops.FINALIZING)
    ops.remove_plan(ops_dir)
    if not staging.final_scan(ops_dir):
        raise PrivacyOperationError("staging leftovers remain; the system remains locked")
    ops.release(ops_dir)

    return ReversalResult(
        operation_id=plan["op_id"],
        subject_id=subject_id,
        display_alias=display_alias,
        privacy_state="ACTIVE",
        files_restored=plan.get("files_restored_count", 0),
        embeddings_regenerated=regenerated,
        embeddings_pending=pending,
        verified=all(v == 0 for v in counts.values()) and all(checks.values()) and pending == 0,
        verification=counts,
        checks=checks,
    )


# ------------------------------------------------------------ the stages' work


def _restore_all(
    source_dir: Path, display_alias: str, original_name: str, original_email: str | None
) -> dict[str, str]:
    """Keys are POSIX-separated (see pseudonymise._rewrite_all's docstring
    for why str(Path(...)) on Windows would break staging.plan_manifest_remap).
    Covers the evidence documents, and external_signals.json for the same
    reason app/privacy/pseudonymise.py's forward direction now rewrites it
    (AGENTS.md 18.0.4)."""
    changed: dict[str, str] = {}
    for path, _kind in enumerate_source_files(source_dir):
        old = path.read_text(encoding="utf-8")
        new = rewrite.restore_text(old, display_alias, original_name, original_email)
        if new != old:
            changed[path.relative_to(source_dir).as_posix()] = new
    signals = source_dir / EXTERNAL_SIGNALS_NAME
    if signals.exists():
        old = signals.read_text(encoding="utf-8")
        new = rewrite.restore_text(old, display_alias, original_name, original_email)
        if new != old:
            changed[EXTERNAL_SIGNALS_NAME] = new
    return changed


def _restore_identity_row(
    conn: sqlite3.Connection, subject_id: str, bundle: IdentityBundle
) -> None:
    # pseudonymised_at/pseudonymisation_operation_id/verification_result_json
    # describe the *current* pseudonymisation state; once reversed there is
    # none, so these are cleared rather than left stale. The full history of
    # both transitions lives in privacy_operations, not on the live row.
    conn.execute(
        "UPDATE people SET privacy_state = 'ACTIVE', display_name = ?, "
        "profile_metadata_json = ?, pseudonymised_at = NULL, "
        "pseudonymisation_operation_id = NULL, verification_result_json = NULL "
        "WHERE subject_id = ?",
        (
            bundle.original_name,
            json.dumps(bundle.profile_metadata) if bundle.profile_metadata else None,
            subject_id,
        ),
    )
    repository.add_alias(conn, subject_id, bundle.original_name, AliasType.FULL_NAME.value)
    for email in bundle.original_emails:
        repository.add_alias(conn, subject_id, email, AliasType.EMAIL.value)
    for alias in bundle.original_aliases:
        # Disclosed fidelity loss (see rewrite.restore_text): the vault does
        # not retain each short form's original alias_type, only the string.
        repository.add_alias(conn, subject_id, alias, AliasType.VARIANT.value)


def _invalidate_alias_dependents(conn: sqlite3.Connection, display_alias: str) -> None:
    """A Case/finding whose stored prose or cited evidence used the alias is
    stale the moment the alias-bearing text is restored to the original
    name; mirrors app/privacy/pseudonymise.py's dependent-invalidation, but
    keyed on the one alias string rather than a Target's full identifier set."""
    for row in list(conn.execute("SELECT case_id, query, receipt_json FROM cases").fetchall()):
        if display_alias in f"{row['query']} {row['receipt_json']}":
            conn.execute("DELETE FROM case_evidence WHERE case_id = ?", (row["case_id"],))
            conn.execute("DELETE FROM cases WHERE case_id = ?", (row["case_id"],))
    for row in list(
        conn.execute(
            "SELECT finding_id, title, summary, finding_json FROM pulse_findings"
        ).fetchall()
    ):
        blob = f"{row['title']} {row['summary']} {row['finding_json']}"
        if display_alias in blob:
            conn.execute("DELETE FROM finding_evidence WHERE finding_id = ?", (row["finding_id"],))
            conn.execute("DELETE FROM pulse_findings WHERE finding_id = ?", (row["finding_id"],))


def _regenerate_stale_embeddings(conn: sqlite3.Connection, provider):
    """Regenerate embeddings for any unit left without one after the
    restore. The SOURCE_DONE stage above already ensures a unit whose text
    changed during the restore comes back from rebuild with no embedding
    row (its old, alias-bearing vector was never restashed), so "missing a
    row" -- not "text still mentions the alias" -- is the correct pending
    signal here: mirrors app/privacy/pseudonymise.py's
    _regenerate_embeddings and its never-hold-a-transaction-open-on-a-
    network-call rule."""
    rows = conn.execute(
        "SELECT e.evidence_id, e.raw_text FROM evidence_units e "
        "LEFT JOIN evidence_embeddings m ON m.evidence_id = e.evidence_id "
        "WHERE m.evidence_id IS NULL"
    ).fetchall()
    if not rows:
        return 0, 0
    if provider is None:
        return 0, len(rows)
    report = generate_embeddings(conn, [(r["evidence_id"], r["raw_text"]) for r in rows], provider)
    conn.commit()
    return report.succeeded, len(rows) - report.succeeded


def _verify(
    conn: sqlite3.Connection,
    source_dir: Path,
    artifact_dirs: list[Path],
    subject_id: str,
    display_alias: str,
    plan: dict,
) -> tuple[dict[str, int], dict[str, bool]]:
    # database_content uses scan_content_rows, not scan_database_rows /
    # scan_database_files: people.display_alias and
    # privacy_operations.display_alias are supposed to retain the alias
    # forever (CLAUDE.md 18.0.7 -- it is only rotated by a separate,
    # explicitly audited operation), so a generic whole-database or
    # raw-file byte scan for the alias would always "fail" on that
    # expected, permanent bookkeeping. What must be zero is the alias
    # appearing in *content* -- source files, evidence/document columns,
    # FTS, Cases, findings.
    counts = {
        "source_files": verify.scan_files(source_dir, [display_alias]),
        "source_filenames": verify.scan_filenames(source_dir, [display_alias]),
        "database_content": verify.scan_content_rows(conn, [display_alias]),
        "artifacts_and_cache": sum(verify.scan_files(d, [display_alias]) for d in artifact_dirs),
        "artifact_filenames": sum(verify.scan_filenames(d, [display_alias]) for d in artifact_dirs),
    }
    active_again = conn.execute(
        "SELECT privacy_state, display_name FROM people WHERE subject_id = ?", (subject_id,)
    ).fetchone()
    surviving = {
        (row["evidence_id"], row["subject_id"], row["relation"])
        for row in conn.execute(
            "SELECT evidence_id, subject_id, relation FROM evidence_people WHERE subject_id = ?",
            (subject_id,),
        )
    }
    pre_relationships = {tuple(x) for x in plan.get("pre_relationships", [])}
    checks = {
        "subject_is_active": bool(active_again) and active_again["privacy_state"] == "ACTIVE",
        "display_name_restored": bool(active_again) and bool(active_again["display_name"]),
        "evidence_people_relationships_preserved": pre_relationships <= surviving,
    }
    return counts, checks
