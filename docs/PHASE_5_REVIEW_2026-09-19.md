# Phase 5 Review — Deletion and Irreversible Anonymization

## Result

**Passed with disclosed deviations.** A person can be irreversibly anonymized
out of the app-owned canonical source and every derived surface; Evidence IDs
of survivors are unchanged; a rebuild cannot resurrect them; the operation is
locked, crash-resumable and verified before it reports success. Two parts of
the v1.5 contract are **not** implemented (below) and one demo decision is
yours. Phase 6 (UI) may begin.

## What was built (`backend/app/privacy/`, `api/privacy.py`)

| Piece | Behaviour |
| --- | --- |
| `targets.py` | Resolves a person and only their **tracked** identifiers (canonical name, reviewed aliases, emails). Whole-token, case- and whitespace-insensitive, Unicode-aware; `Ann Lee` never damages `Joann Leeds` |
| `redact.py` | Role-aware source redaction: speaker-marker lines → `[REDACTED SPEAKER]`, `From/Von/Från` → `[REDACTED SENDER]`, recipients/inline → `[REDACTED PERSON]`, Attendees entry removed, initials chrome removed, signature block removed, names hard-wrapped across lines caught by a final sweep |
| `service.py` | preview / purge / recover. Stages: lock → plan → manifest remap + atomic source replace → rebuild through the normal ingestion path → invalidate dependent Cases/findings → WAL checkpoint + VACUUM + empty derived folders → verify → remove plan → release lock |
| `ops.py` | Exclusive lock, atomic same-directory file replacement, recorded states, 0700/0600 permissions; startup recovery resumes by state, clears an orphan `PLANNING` lock, finishes a `FINALIZING` lock with the plan already gone, and fails closed on anything else |
| `verify.py` | Scans source files, every text column of every table, the `.db`/`-wal`/`-shm` bytes, and artifact/cache folders for the tracked identifiers; counts only |
| API | `GET /api/privacy/people`, `POST /api/privacy/preview`, `POST /api/privacy/purge` (needs `confirm: true`; returns counts and verification, never content). Serving and `scripts/ingest.py` refuse while a lock exists |

Supporting fixes found by the work:

- **Rebuild destroyed the dependency record.** Dropping `evidence_units`
  cascade-deleted every `case_evidence` row on any rebuild. The reset now drops
  with foreign keys off, so Case dependencies survive (regression-tested).
- **Adjacent redacted speakers fused.** After two people are removed, their
  neighbouring turns share the generic label and the Phase 1 merge rule fused
  them, making an Evidence ID disappear. Group boundaries are now persisted in
  `source_locators.starts_group` (recorded before redaction, including a
  backfill for databases that predate the column), so boundaries no longer
  depend on a speaker label.
- Embeddings: vectors of text that mentions the person are dropped; all others
  are stashed and restored by matching `text_hash`; changed survivors are
  regenerated after verification, while still locked. With no provider they stay
  absent and are reported as pending — never stale.

## Verification

- 312 backend tests, Ruff clean, frontend typecheck passes. 45 privacy tests
  run on a synthetic corpus in temporary instances only (CLAUDE.md 0.5).
- **Real archive, temporary copy** (never the repo's `data/`): Kwame Boateng and
  Priya Nair each removed in turn — all 2,517 Evidence IDs identical, every
  verification surface 0, no parse warnings, full name absent from source, still
  absent after a normal rebuild. Kwame: 18 files, 97 units affected, 77
  speaker turns → `[REDACTED SPEAKER]`. Priya: 30 files, 352 units. About 1 s
  with the mock embedder.
- Haiku reviewers: the auditor's findings were mostly invalid on inspection
  (stash reuse is what makes resume work and is `text_hash`-guarded; the final
  scan and verifier already cover what was claimed). Valid ones were fixed
  (file permissions; reset the shared index after startup recovery). The
  adversarial tester's report contained a fabricated-looking hash, so it was
  discarded and the probes were written as real tests, one of which found a
  genuine gap (hard-wrapped names), now fixed.

## Deviations from the frozen v1.5 contract — not hidden

1. **No whole-unit deletion and no locator revocation.** Redaction is applied
   in place (the step-3 upper bound). A unit that redaction empties stays as a
   marker-only placeholder. So 18.6 step 4 and 18.8's tombstones, including
   merged-transcript constituents, are unimplemented; the existing
   `revoke_source_locator` primitive is unused. The exit line "fully deleted
   evidence is absent" is therefore vacuous, not demonstrated.
2. **The operation plan stores the person's identifiers** (18.11 asks for a
   minimal plan). They are needed so verification can resume after a crash once
   the person's rows are gone. The plan is deleted and confirmed gone before the
   lock is released, and is 0600 in a 0700 folder.
3. **Not implemented:** the replay-based source-span resolver (18.9). The
   sanitizer works on file text and is checked by re-parsing (a changed unit
   count aborts before anything is committed).

## Decision needed from you (judge-demo risk)

Only *tracked* identifiers are removed. A bare first name that has not been
reviewed into `data/source/reviewed_identities.json` is left alone, because it
may be someone else. For Kwame Boateng, **13 bare "Kwame" mentions remain**
after the operation as the repo stands; with a reviewed first-name alias none
do. Before a live demo, add reviewed short-form aliases for the people a judge
may pick. I did not edit the canonical manifest — that is a human-review step.

## Known risks carried forward

- Verification proves absence of *known* identifiers only; it is not proof that
  no unknown nickname or indirect reference exists, and not cryptographic erasure.
- Signature-block removal drops up to six non-blank lines under a bare name line.
- `.git` history still contains the pre-sanitization corpus (documented
  boundary, CLAUDE.md 18.1.1); the app never reads it.
- Recompute of affected Cases with the reasoning model is left to the caller
  (invalidated Cases are simply gone); the UI (Phase 6) re-asks.
