# CLAUDE.md — KEEPER: Evidence-First Organizational Memory Auditor

> **Status:** Architecture v1.6 FROZEN — the evidence/reasoning foundation exists, but the previous Phase 5 privacy implementation is rejected and superseded. The 2026-09-19 audit at `f48a666` recorded 368 passing and 22 failing backend tests (all in deletion/deletion-dependent behavior), a stale runtime database with zero embeddings, and a fresh ingest of 2,534 units. The next implementation must build judge-required stable pseudonymisation with preserved relationships and an isolated reversal vault; do not extend the old generic-marker deletion path.
> **Challenge:** RELEX Solutions — “Memory With a Receipt”
> **Project:** KEEPER
> **Build model:** 1 developer, ~40 total working hours, AI-assisted implementation
> **Primary objective:** Build the smallest reliable system that can reconstruct organizational truth from a small archive, prove every conclusion with evidence, expose conflicts and supersession, and pseudonymise a participant while preserving their complete attributable history and relationship graph.

---

# 0. READ THIS FIRST

This file is the implementation contract.

Do **not** redesign the architecture unless a concrete blocker makes the specified implementation impossible. Do not add frameworks because they seem architecturally elegant. Do not optimize for hypothetical enterprise scale.

The priority order is:

1. Reliability in a live judge demo.
2. Correct evidence provenance.
3. Correct attribution and current-state reasoning.
4. Correct pseudonymisation, profile history, vault isolation, and post-operation recalculation.
5. Debuggability.
6. Clear product value.
7. Polish.
8. Performance optimization only when necessary.

The archive is small: approximately 45 documents / 57,000 words spanning March 2024–July 2026. The system will be tested using unreleased judge questions and a live personal-data deletion.

The central invariant is:

> **The Evidence Locker is the memory. The LLM is only an interpreter.**

Raw evidence is authoritative. LLM annotations, summaries, stances, conclusions, and receipts are derived interpretations and may be wrong.

---


# 0.1 CURRENT IMPLEMENTATION CHECKPOINT

This section reflects the audited repository baseline at `f48a666` on 2026-09-19. It is not a claim that the legacy privacy implementation is acceptable for the demo.

## Completed

- Repository inspected against the real challenge corpus.
- Corpus confirmed as 45 evidence documents:
  - 20 email threads,
  - 2 report threads,
  - 23 transcripts.
- Frontend scaffold exists and has been verified with a successful Vite/TypeScript build.
- FastAPI health/config scaffold exists.
- `.gitignore`, `.env.example`, and README scaffolding exist.
- Python is now installed and available.
- `data/source/` contains the **application-owned canonical working copy** of the 45 challenge evidence documents.
- `data/ARCHIVE_README.md` and `data/PRACTICE_QUESTIONS.md` exist as non-evidence reference material.
- Git repository has been initialized.
- Git remote `origin` is configured for `https://github.com/vietdoan0233/RelexChallenge.git`.
- Phase 0 is complete: backend/frontend boot, tests, lint, typecheck, and build have passed.
- Phase 1 implementation exists for:
  - SQLite schema and repository layer,
  - stable source-locator manifest and Evidence IDs,
  - named Teams, anonymous INTERNAL, email-thread, and report parsing,
  - truncation preservation,
  - people/aliases and `evidence_people`,
  - FTS5 population,
  - provider-neutral embedding interface, deterministic mock, and `--skip-embeddings`,
  - bounded embedding batches, exponential retry, vector validation, and a clear partial-failure report,
  - OpenAI-compatible `/v1/embeddings` provider adapter with safe status/request-ID logging,
  - ingestion CLI/report,
  - unit and integration tests.
- The audit's fresh isolated ingestion parsed 45 documents into 2,534 Evidence Units and 2,534 FTS rows.
- The audit recorded 25 people, 41 aliases, and 1,966 speaker relationships in the fresh ingest.
- The audited quality gate was 368 passing and 22 failing backend tests; every failure was in legacy deletion or deletion-dependent Radar behavior. Ruff, frontend type-check, frontend lint, and production build passed.
- The checked-in runtime database was stale and contained 2,517 Evidence Units but zero embeddings. It must be rebuilt before any judge rehearsal.
- Phase 1 identity hardening is complete: `people`/`person_aliases` are rebuilt every ingestion run from `data/source/` plus a human-reviewed identity manifest (`data/source/reviewed_identities.json`); a capitalized free-text span is never auto-promoted to `people`; short-form aliases (first name, last name, initials, nicknames, spelling variants) are promoted only through an explicit reviewed manifest entry with its own alias_type and source_reference, never from uniqueness or independent corpus usage alone.

## Important corpus discoveries already verified

### Anonymous INTERNAL transcripts

Three transcript files use an anonymous `Me:` / `Them:` dialogue format instead of normal named Teams-style speaker exports.

Rules:

- do not infer real identities for `Me` or `Them`,
- preserve the literal anonymous speaker label or an explicit anonymous-speaker identifier,
- do not map those turns to roster people merely because a likely identity seems plausible,
- people named inside the content may still be recorded as `MENTIONED`.

### Teams transcript formatting

Normal transcript exports may contain:

- duplicated timestamp/UI text,
- initials as UI chrome,
- consecutive caption fragments from the same speaker belonging to one semantic turn.

Parsers should remove known UI chrome deterministically and merge consecutive fragments only when the source structure clearly indicates they belong to the same uninterrupted turn.

Never “repair” meaning while normalizing.

### Truncated source statements

The corpus intentionally contains cut-off statements, including partial numeric statements.

A parser must preserve truncation rather than complete or infer missing text.

Add an Evidence Unit field such as:

```text
is_truncated: boolean
```

Reasoning prompts must treat a truncated unit as incomplete evidence and must never complete the missing sentence/number.

### Email image placeholders

Image placeholders are not represented by one universal string. Known examples include multiple English forms, `cid:` references, bare `Image`, and a Swedish placeholder.

Do not make parsing dependent on one exact placeholder token.

## Phase state

**Phase 1 is implemented but the runtime artifact is stale.** The audit's fresh ingest is the current corpus baseline: 2,534 Evidence Units and 2,534 FTS rows. A release/readiness step must rebuild and verify embeddings rather than trusting the gitignored runtime database.

**Phases 2–4, 6, and 7 have implementation work and review artifacts, but the product is not demo-ready.** Retrieval still has known answer-quality misses and the audit found the legacy privacy path broken on Windows, unauthenticated, and incomplete for arbitrary targets. **Phase 5 is explicitly reset:** its generic-marker deletion/anonymisation behavior is legacy and must be replaced by Architecture v1.6 pseudonymisation. The planned build is not finished until the new privacy/profile/vault contract passes.

Identity hardening is resolved: capitalized free-text phrases can no longer become deletion-relevant identities, and the resulting people/alias/evidence-person counts have been reviewed against the corpus (see below). The two items that remained open — real full-corpus embeddings and a corrected Phase 1 review — were resolved (`docs/PHASE_1_REVIEW_2026-09-19.md`).

The audit's fresh offline ingest produced 25 people and 41 aliases, with 1,966 speaker relationships. The legacy identity layer still derives `person_id` from names and is therefore not an acceptable identity foundation for the new contract. The replacement must migrate to random `subject_id` values, stable cryptorandom `display_alias` values, and evidence relationships that survive pseudonymisation.

Architecture v1.6 supersedes the old Phase 5 contract. The new privacy operation writes a stable per-person alias into the canonical source and all derived public representations, preserves `evidence_people` and the complete profile history, and stores the original identity only in a separately encrypted vault. The original names, emails, aliases, generic redaction markers, name-derived IDs, and old locator-revocation strategy are not implementation targets for the new operation.

---

# 0.2 GITHUB WORKFLOW

The local repository uses the configured `origin` remote. Connector availability varies by session and must be verified rather than assumed.

Claude may inspect and synchronize the configured `origin` remote when the task requires it. Remote operations are allowed, but must follow the checks below and must never overwrite unrelated work.

## Required first checks

Before making repository-history changes:

1. inspect the local git status,
2. inspect configured remotes,
3. use local tracking information or an available read-only GitHub connection to verify the intended repository/branch,
4. compare local staged/uncommitted work with the remote before pushing,
5. do not overwrite unrelated remote changes.

## Commit/push behavior

Commit completed work in small, tested batches. After writing or changing code, configuration, tests, or repository instructions:

1. inspect the diff and confirm that unrelated user changes are not included,
2. run the relevant tests, linters, type checks, or build checks,
3. create a focused local commit before sending the response.

Every response that reports completed changes must leave those changes committed. Do not create an empty commit when no files changed. If a check or commit cannot be completed, say so explicitly and leave the work safely staged or unstaged rather than claiming completion.

Claude may run `git fetch`, `git pull`, and `git push` when needed for the requested task. Before synchronization:

- inspect status, the current branch, configured remotes, and ahead/behind state,
- preserve or commit local work before pulling; do not silently discard it,
- prefer fast-forward-only pulls unless the user explicitly asks for merge or rebase behavior,
- review the resulting diff and run relevant checks after a pull,
- push only the intended branch and report the exact remote/branch updated.

If a pull produces conflicts, or a push is rejected because the remote advanced, stop and report the conflict or divergence. Do not force-push unless the user explicitly requests it.

If local `git commit` is used and identity is missing:

- do not invent an email/name,
- do not change global git identity,
- use a verified connector/account identity only if it is explicitly exposed and appropriate,
- otherwise leave the changes staged/uncommitted and report the commit blocker,
- **missing git identity must never block Phase 1 implementation, testing, or local progress.**

Never rewrite existing remote history for convenience.

## Current history and next milestone

Verified local history at this checkpoint:

1. `5886ab5 chore(scaffold): establish keeper phase 0 baseline`
2. `1c6f3d7 feat(ingestion): build evidence locker and stable source parsing`
3. `1bb96b1 fix(ingestion): strip bullet numbering in single-bullet report sections`
4. `c56c252 docs: record phase 1 checkpoint and handoff`
5. `0260ef9 chore(config): prepare organizer GPT provider`
6. `8c6b79b fix(ingestion): harden identities and make branding configurable`

At this checkpoint, `8c6b79b` is committed locally and currently unpushed. This is a point-in-time observation about repository state, not a standing architectural rule about where local history must sit relative to `origin/main`.

Phases 1–7 are complete (section 0.1). The Architecture v1.5 deletion/anonymization documentation (section 0.3, section 18) is a separate contract correction for future Phase 5 work — it is not part of the Phase 1–2 milestones above.

Use an available GitHub connection for repository work such as:

- verifying remote repository state,
- inspecting branch/history,
- reviewing diffs,
- fetching, pulling, and pushing when required by the task.

Do not let GitHub integration change the architecture or source-of-truth rules.

# 0.3 CONTRACT VERSION HISTORY

The architecture version changes only when the frozen product or technical architecture changes. Updating implementation progress, repository state, test counts, or handoff notes does **not** create a new architecture version.

- **v1.6 — current, frozen.** Replaces the rejected generic-marker deletion design with judge-required robust pseudonymisation. Every participant has a random internal `subject_id`, a stable cryptographically random `display_alias` such as `Participant Q7M4-N8`, and a `privacy_state`. Pseudonymisation preserves every Evidence Unit, `evidence_people` relationship, Evidence ID, and clickable full-history profile; it rewrites direct identifiers and structural attribution to the per-person alias. The original identity is retained only as encrypted data in a strictly isolated reversal vault. Main audit records contain the subject ID, alias, state, timestamps, operation ID, and verification result, never the original name. Standard queries, FTS, embeddings, caches, and logs cannot access the vault. Reversal is a separately authenticated admin workflow, not a standard profile/search capability. Implementation is pending; the old Phase 5 code is superseded and must not be debugged into compliance.
- **v1.5 — superseded.** The former irreversible generic-marker redaction/whole-unit-deletion contract is retained only as historical context. Its `[REDACTED ...]` markers, name-derived `person_id`, cascading person deletion, locator revocation, and “zero surviving identifier” success criteria are not part of v1.6.
- **v1.4 — previous frozen architecture.** Replaced the Google/Gemini provider choice with an organizer-provided GPT service. The API key, base URL, reasoning model, and embedding model remain environment placeholders until the organizers supply the exact contract. The provider-neutral offline ingestion path remains mandatory.
- **v1.3 — earlier frozen architecture.** Audited architecture contract covering the Phase 0 checkpoint, GitHub workflow, stable source-locator manifest, canonical-source rebuild invariant, embedding resilience, citation-context invariant, Skeptic counter-retrieval behavior, deletion cleanup, and mandatory Phase 1 review gate.
- **2026-09-19 implementation checkpoint — no architecture version change.** Recorded the implemented Phase 1 Evidence Locker, verified offline ingestion/test counts, known identity-discovery false positives, missing real embeddings, and the decision to stop before Phase 2.
- **2026-09-19 identity/documentation correction pass — no architecture version change.** Fixed a short-alias independence check that only looked backward from a candidate's match position (so a first name at the start of its own full name was wrongly treated as independently observed, while the corresponding last-name case was already correct); replaced heuristic short-alias promotion with an explicit reviewed-alias mechanism (uniqueness and independent corpus usage are review signals, not promotion criteria on their own); restructured the reviewed identity manifest to avoid duplicating raw quotations or naming unrelated people, so deleting one person's entry never requires editing another; reordered ingestion to validate parsed source files and the reviewed identity manifest before the destructive rebuildable-table reset, so a malformed manifest fails loudly instead of emptying the database first; corrected documentation that overstated the rebuild reset as covering "every table except source_locators" when Cases/Pulse tables are untouched and not yet implemented; removed a remaining hardcoded codename from backend package metadata; and corrected stale checkpoint numbers below. See section 0.5 for the destructive-test isolation contract added in this pass.

Earlier architecture iterations are not reconstructed here because their authoritative change notes are not present in the repository. Do not invent retrospective version details.

# 0.4 BRANDING NEUTRALITY

“KEEPER” is a temporary project codename, not a frozen brand. The final product will use a different name. This branding clarification does not itself change the architecture version and remains unchanged under Architecture v1.5.

Rules:

- runtime behavior and persistent identifiers must not depend on the codename,
- user-facing and configurable surfaces (API title, frontend title/heading, CLI descriptions, default database filename, package metadata) must read from configuration or use neutral functional terminology, never a hardcoded “KEEPER”,
- use `APP_NAME` (backend) and `VITE_APP_NAME` (frontend) for a configurable display name, falling back to a neutral name such as “Organizational Memory Auditor” when unset,
- the default runtime database filename is a neutral `data/app.db`, not `data/keeper.db`,
- historical architecture, handoff, and challenge documentation may retain “KEEPER” when identifying the existing codename — this file, `AGENTS.md`, and `docs/HANDOFF_*.md` are not rewritten to remove it,
- do not invent the final product name; use neutral terminology until one is chosen,
- do not rename the repository.

# 0.5 TEST ISOLATION AND DESTRUCTIVE-TEST SAFETY

The new Phase 5 pseudonymisation operation and tests are inherently destructive to the identity-bearing source/database they run against. This section is the binding contract for those tests, so development work can never permanently rewrite the repository's own canonical source, a runtime database intended for judges, or an already-prepared demo instance.

Three distinct concepts:

1. **Development fixture/reference** — the pristine, untouched hackathon archive kept outside `data/source/` and outside application-owned persistence (gitignored). It exists only to be copied from when creating an isolated development/test environment. It must never become a runtime fallback after pseudonymisation, and normal ingestion/rebuild must never read it directly (see section 7's canonical-source boundary).
2. **Test instance** — a temporary copy of the required canonical source, created fresh per test in a location the test framework owns (e.g. pytest `tmp_path`), with its own temporary database, artifacts directory, and cache directory. Destructive tests may modify only this temporary instance.
3. **Judge/demo instance** — the repository's real `data/source/`, real runtime database (`data/app.db`), vault, and their real artifacts/cache directories, initialized from a clean canonical source copy. A judge-requested pseudonymisation against this instance is intentionally persistent and reversible only through the authenticated admin workflow.

**Binding test rule.** Every test that modifies source content, pseudonymises a person, exercises vault reversal, or simulates rebuild must:

1. create a temporary directory using the test framework,
2. copy only the required source fixture into it,
3. configure `SOURCE_DATA_DIR`, `DATABASE_PATH`, artifact paths, and cache paths so they point inside that temporary directory,
4. ingest into its temporary database,
5. perform privacy work only against that temporary source, database, and vault,
6. verify public database/source/index/artifact cleanup and relationship/profile preservation,
7. rebuild only from the temporary alias-bearing source,
8. verify the original identity is not resurrected and the subject is not lost,
9. discard the temporary instance afterward.

A destructive/privacy test must never write to `<repository>/data/source/`, `<repository>/data/app.db`, `<repository>/data/keeper.db`, or a real vault.

Existing read-only integration tests may inspect the canonical corpus directly if they never modify it and use an isolated/in-memory database; there is no need to copy the full archive for a purely read-only test. `backend/tests/conftest.py`'s `isolated_instance` fixture provides a ready-made temporary on-disk instance (source directory, database, artifacts directory, cache directory, and vault, all under `tmp_path`) for privacy tests that need real on-disk behavior, rather than the in-memory `conn` fixture used for pure logic tests.

This section does not implement the v1.6 operation. It fixes the isolation contract pseudonymisation and reversal tests must follow once implementation begins.

# 1. PRODUCT MISSION

KEEPER is an **AI Organizational Memory Auditor**.

It should not feel like “ChatGPT over company documents.”

Its job is to answer:

- What actually happened?
- What was merely proposed versus actually agreed?
- What is currently true?
- What was later contradicted or superseded?
- Which evidence supports each conclusion?
- What evidence conflicts with it?
- Why did the system choose one interpretation?
- What remains uncertain?
- What happens to organizational memory when a person’s evidence is deleted?

Every arbitrary user query creates or opens a **Case**.

A Case contains:

- a supported conclusion,
- claim-level evidence,
- conflicting evidence,
- stance / attribution,
- uncertainty,
- conflict resolution,
- Decision Evolution timeline where useful,
- original source receipts,
- post-deletion recalculation when relevant.

---

# 2. AUTHORITATIVE CHALLENGE CONSTRAINTS

Preserve these rules in implementation and prompts.

## 2.1 Provenance

Every important factual claim must point to stored evidence.

Citation specificity only needs to be human-auditable:

- source document,
- date,
- speaker/sender where applicable,
- meeting/email/thread context,
- exact source text shown from the database.

Do not spend hackathon time on cryptographic/Merkle/token-level provenance.

## 2.2 Attribution

The system must distinguish:

- suggestion,
- proposal,
- assumption,
- objection,
- discussion,
- agreement,
- commitment,
- status update,
- implementation evidence,
- supersession,
- uncertainty.

**There is no hardcoded authority hierarchy.**

Never encode:

```text
PERSON_X = APPROVER
```

Never require a specific named person to assent before something can count as an agreement.

Whether something became an agreement/decision must be inferred from the conversational evidence itself.

## 2.3 Currency

Newer information is not automatically more truthful.

A recent management/status report may conflict with older or same-period operational evidence.

When evidence conflicts:

1. expose the conflict,
2. explain why one interpretation is stronger,
3. do not silently average contradictions,
4. distinguish stale/superseded from false/unverified.

## 2.4 Robust pseudonymisation

Architecture v1.6 replaces the rejected deletion/generic-redaction design with judge-required pseudonymisation. The operation must preserve organizational evidence and the participant's complete attributable history while removing the original identity from ordinary application surfaces.

Every participant has this public identity contract:

```yaml
subject_id: random internal UUID
display_alias: Participant Q7M4-N8
privacy_state: ACTIVE | PSEUDONYMISED
```

Rules:

- `subject_id` is generated with a cryptographically secure random UUID and contains no name-derived material. It is the stable relational key everywhere; do not use a slugified name as an ID.
- `display_alias` is generated independently with a cryptographically secure random generator, is unique, stable across rebuilds, and is never derived from a name, hash, employee number, title, or sequence. Collision handling retries generation; it never increments a predictable counter.
- Pseudonymisation rewrites the application-owned canonical source and all public derived representations to the participant's own alias, including speaker/sender fields, email headers, attendee lists, signatures, inline mentions, and identifying structured metadata.
- Records remain personal data after pseudonymisation. Do not describe this as irreversible anonymisation or universal legal/GDPR compliance.
- The participant row and every `evidence_people` relationship survive. Do not cascade-delete a person to make the operation appear complete.
- Keep `pseudonymised_at`, operation ID, and verification result in the public audit record, but never store the original name in that audit record.
- Generic labels such as `[REDACTED PERSON]`, `[REDACTED SPEAKER]`, and `[REDACTED SENDER]` are retired for participant pseudonymisation. They destroy person-level linkage and cannot satisfy the profile requirement. Corpus-native anonymous labels such as `Me`, `Them`, and `Guest 1` remain distinct and are not converted into people.
- Affected Cases, receipts, timeline events, FTS rows, embeddings, caches, and Pulse findings are invalidated or rebuilt from the alias-bearing surviving evidence. Affected conclusions are recalculated.

The original identity is not searchable through normal APIs. It exists only in the encrypted, isolated reversal vault described in section 18.0.3, and only the explicit authenticated admin reversal workflow may read it.

## 2.5 Initiative

The product must be more than an empty chat screen.

Core standout feature: **Decision Evolution**.

Optional/stretch proactive feature: **Project Pulse**.

---

# 3. FROZEN ARCHITECTURE

The core query path is:

```text
USER QUESTION
    ↓
HYBRID RETRIEVAL
    ↓
PRIMARY REASONER
    ↓
STRUCTURED CANDIDATE CLAIMS
    ↓
RISK ENGINE
    ↓
┌─────────────────┬─────────────────────────┐
│ LOW RISK        │ MEDIUM/HIGH RISK        │
│                 │                         │
│ direct receipt  │ Skeptic                 │
│                 │     ↓                   │
│                 │ counter-retrieval       │
│                 │     ↓                   │
│                 │ Primary reconciliation  │
└────────┬────────┴────────────┬────────────┘
         └──────────┬──────────┘
                    ↓
             STRUCTURED RECEIPT
                    ↓
          DETERMINISTIC VALIDATOR
                    ↓
                CASE UI
```

There are only two conceptual AI roles:

1. **Primary Reasoner**
2. **Conditional Skeptic**

The Primary Reasoner also performs final reconciliation after Skeptic results.

Do not add:

- CrewAI,
- AutoGen,
- LangGraph unless an existing repository already depends on it and removing it is more costly,
- a three-agent debate framework,
- autonomous tool-using agent loops,
- Neo4j,
- microservices,
- distributed queues,
- Slack/Teams integration,
- RBAC/multi-tenancy.

---

# 4. LOCKED TECH STACK

No unresolved “X or Y” choices.

## Backend

- Python 3.11+
- FastAPI
- Pydantic v2
- SQLite
- SQLite FTS5
- NumPy
- organizer-provided GPT API directly; exact SDK/transport is added only after the organizers supply the endpoint contract
- pytest
- Ruff
- python-dotenv

## Retrieval

- lexical: SQLite FTS5 (`bm25`)
- semantic: embeddings stored in SQLite + NumPy cosine similarity
- fusion: deterministic rank fusion
- context: neighbor expansion from the same source/thread
- temporal: later-evidence sweep for decision/current-state queries

Do **not** introduce a dedicated vector database. The corpus is too small to justify it.

## Frontend

- React
- Vite
- TypeScript
- Tailwind CSS
- TanStack Query
- minimal component dependencies only

Do not add Zustand unless a concrete state problem requires it. Prefer local state + TanStack Query.

## LLM configuration

Use environment variables:

```env
GPT_API_KEY=
GPT_BASE_URL=
GPT_MODEL=
GPT_EMBEDDING_MODEL=
DATABASE_PATH=./data/app.db
SOURCE_DATA_DIR=./data/source
PSEUDONYM_VAULT_PATH=./data/private-vault/vault.db.enc
PSEUDONYM_VAULT_KEY=
```

`.env.example` is a committed, secret-free template and must remain tracked. Real credentials belong only in the gitignored root `.env`.

Do not hardcode model names in business logic.

All LLM calls must have:

- timeout,
- explicit structured schema,
- bounded retries,
- logged request ID/status but **not persisted raw prompts/responses containing personal data**.

---

# 5. REPOSITORY TARGET MAP

Use this layout unless the existing repository already has a sensible equivalent.

```text
relex-keeper/
├── CLAUDE.md
├── README.md
├── .env.example
├── .gitignore
│
├── data/
│   ├── source/                  # canonical imported source under app control
│   ├── app.db                   # runtime DB, gitignored
│   ├── private-vault/            # encrypted reversal vault, gitignored and isolated
│   ├── artifacts/               # derived runtime artifacts, gitignored
│   └── cache/                   # disposable cache, gitignored
│
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── enums.py
│   │   │   └── errors.py
│   │   │
│   │   ├── db/
│   │   │   ├── connection.py
│   │   │   ├── schema.sql
│   │   │   ├── migrations.py
│   │   │   └── repository.py
│   │   │
│   │   ├── ingestion/
│   │   │   ├── service.py
│   │   │   ├── parsers/
│   │   │   │   ├── transcript.py
│   │   │   │   ├── email.py
│   │   │   │   └── report.py
│   │   │   ├── people.py
│   │   │   └── embeddings.py
│   │   │
│   │   ├── retrieval/
│   │   │   ├── lexical.py
│   │   │   ├── semantic.py
│   │   │   ├── fusion.py
│   │   │   ├── context.py
│   │   │   ├── temporal.py
│   │   │   └── service.py
│   │   │
│   │   ├── reasoning/
│   │   │   ├── prompts.py
│   │   │   ├── primary.py
│   │   │   ├── risk.py
│   │   │   ├── skeptic.py
│   │   │   ├── reconcile.py
│   │   │   └── service.py
│   │   │
│   │   ├── validation/
│   │   │   └── receipt_validator.py
│   │   │
│   │   ├── timeline/
│   │   │   └── evolution.py
│   │   │
│   │   ├── privacy/
│   │   │   ├── pseudonymise.py
│   │   │   ├── profile.py
│   │   │   ├── vault.py
│   │   │   ├── dependencies.py
│   │   │   └── verify.py
│   │   │
│   │   ├── pulse/
│   │   │   └── service.py      # optional/stretch only
│   │   │
│   │   ├── schemas/
│   │   │   ├── evidence.py
│   │   │   ├── reasoning.py
│   │   │   ├── receipt.py
│   │   │   ├── privacy.py
│   │   │   └── api.py
│   │   │
│   │   └── api/
│   │       ├── cases.py
│   │       ├── evidence.py
│   │       ├── privacy.py
│   │       └── pulse.py        # optional/stretch
│   │
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── evaluation/
│
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   │   ├── case/
│   │   │   ├── evidence/
│   │   │   ├── timeline/
│   │   │   └── privacy/
│   │   ├── pages/
│   │   │   ├── AskPage.tsx
│   │   │   ├── CasePage.tsx
│   │   │   └── PrivacyPage.tsx
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── ...
│
└── scripts/
    ├── ingest.py
    ├── rebuild.py
    └── benchmark.py
```

---

# 6. DEVELOPMENT COMMANDS

Prefer a single clear setup path.

## Backend

```bash
cd backend

python -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev -- --port 3000
```

## Tests / lint

```bash
cd backend
pytest -q
ruff check app tests
ruff format --check app tests
```

```bash
cd frontend
npm run typecheck
npm run build
```

## Ingestion / rebuild

Expose simple commands such as:

```bash
python ../scripts/ingest.py --source ../data/source
python ../scripts/rebuild.py
python ../scripts/benchmark.py
```

If the repository structure makes module invocation cleaner, prefer:

```bash
python -m app.cli.ingest
```

but choose one style and document it in README. Do not maintain two redundant CLI systems.

---

# 7. CORE DATA MODEL

## 7.1 Evidence Unit, not arbitrary chunk

The fundamental retrieval object is an **Evidence Unit**.

Preferred boundaries:

- transcript → one speaker turn,
- email thread → one individual email/message,
- report → one bullet point, short sub-paragraph, or the smallest coherent factual section.

**Profile/history rule:** Evidence Units should be as small as practical without destroying meaning. Fine boundaries make every participant's full history and contribution quotes inspectable, allow precise alias substitution, and keep citation provenance intact. Do not store an entire multi-bullet engineering/status section as one Evidence Unit if the bullets can stand independently.

Long units may be split, but they must retain the same source relationship, parent document, sequence, and neighbor relationships.

Do not default to blind fixed-token chunking.

The reason for this granularity is profile fidelity as well as retrieval quality: pseudonymising one person must not lose unrelated facts that happened to share a large coarse chunk.

## 7.2 Required tables

Implement a compact relational model similar to:

```sql
CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    document_type TEXT NOT NULL,
    title TEXT,
    source_date TEXT,
    thread_context TEXT
);

CREATE TABLE evidence_units (
    evidence_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    unit_index INTEGER NOT NULL,
    speaker_sender TEXT,
    event_date TEXT,
    timestamp_text TEXT,
    thread_context TEXT,
    raw_text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    UNIQUE(document_id, unit_index)
);

CREATE TABLE people (
    subject_id TEXT PRIMARY KEY, -- cryptographically random UUID; never a name slug
    display_alias TEXT NOT NULL UNIQUE,
    privacy_state TEXT NOT NULL CHECK (privacy_state IN ('ACTIVE', 'PSEUDONYMISED')),
    display_name TEXT,           -- populated only while ACTIVE
    profile_metadata_json TEXT,  -- active metadata; no original PII after pseudonymisation
    pseudonymised_at TEXT,
    pseudonymisation_operation_id TEXT,
    verification_result_json TEXT
);

CREATE TABLE person_aliases (
    alias_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES people(subject_id) ON DELETE RESTRICT,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,    -- FULL_NAME | EMAIL | REVIEWED | DISPLAY_ALIAS
    UNIQUE(subject_id, alias)
);

CREATE TABLE evidence_people (
    evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL REFERENCES people(subject_id) ON DELETE RESTRICT,
    relation TEXT NOT NULL, -- AUTHOR | SPEAKER | MENTIONED
    PRIMARY KEY (evidence_id, subject_id, relation)
);

CREATE TABLE privacy_operations (
    operation_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES people(subject_id) ON DELETE RESTRICT,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    display_alias TEXT NOT NULL,
    pseudonymised_at TEXT,
    verification_result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- The original identity is deliberately NOT in the main SQLite schema. It is
-- stored as encrypted ciphertext in the separate vault described in section
-- 18.3 and is inaccessible to ordinary repositories, FTS, embeddings, and logs.

CREATE TABLE evidence_embeddings (
    evidence_id TEXT PRIMARY KEY REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    vector_json TEXT NOT NULL
);

CREATE TABLE cases (
    case_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE case_evidence (
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    usage TEXT NOT NULL, -- SUPPORT | CONFLICT | TIMELINE
    PRIMARY KEY(case_id, evidence_id, usage)
);

CREATE TABLE pulse_findings (
    finding_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    finding_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE finding_evidence (
    finding_id TEXT NOT NULL REFERENCES pulse_findings(finding_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    PRIMARY KEY(finding_id, evidence_id)
);
```

Create an FTS5 virtual table tied to evidence units. Keep FTS synchronization deterministic.

Exact DDL may be adjusted for SQLite constraints, but preserve these relationships.

## 7.3 Stable evidence IDs

### Persistent source-locator manifest

For plain-text sources that do not provide a naturally stable message/turn identifier, KEEPER should maintain a lightweight persistent source-locator manifest during first canonical ingestion.

Recommended concept:

```text
document_id
source_locator
source_fingerprint
original_order
```

Rules:

- `source_locator` is assigned once and preserved for the life of that surviving source unit,
- deleting an earlier unit must not renumber later locators,
- mutable line numbers or `bullet_0`, `bullet_1`, `bullet_2` are not sufficient identities by themselves,
- a content hash/fingerprint may help match units during sanitation/rebuild, but **content hash alone is not a safe identity** because duplicate/near-duplicate text may occur,
- if a natural stable identifier exists (email message ID, transcript timestamp/turn locator), prefer it over a generated manifest locator,
- sanitation/rebuild must preserve locators for unaffected surviving units.

A practical implementation may use a small sidecar JSON/SQLite manifest tied to the canonical `data/source/` representation.

Add tests proving that:

```text
initial ingest
→ delete one earlier unit
→ rebuild
→ unaffected surviving units keep the same evidence_id
```


Evidence IDs must remain stable across normal re-ingestion and deletion/rebuild whenever the underlying surviving source unit is the same.

Do **not** derive IDs only from the current ordinal position of a unit, because deleting an earlier unit could renumber every later unit.

Preferred strategy:

```text
evidence_id = stable(document_id + source_locator)
```

Where `source_locator` is a persistent locator captured from the original parsed source structure, for example:

- transcript turn locator,
- email message locator,
- report bullet/sub-paragraph locator,
- source line/range locator when appropriate.

A deterministic hash of `document_id + source_locator` is acceptable.

The key invariant is:

> deleting one Evidence Unit must not cause unrelated surviving Evidence IDs to change.

If exact source locators are not naturally present, assign them once during canonical ingestion and persist them in the sanitized app-owned source/manifest used for rebuilds.

Do not regenerate locators by compacting surviving units after deletion.

A unit that is pseudonymised keeps its existing Evidence ID and locator; only the identifying content and public participant fields change. Pseudonymisation must not delete the unit or revoke its locator, because the complete history and clickable profile depend on those stable references.

---


## Canonical source boundary for this hackathon

`data/source/` is KEEPER's **application-owned canonical working source** for ingestion, rebuild, and pseudonymisation behavior.

The untouched challenge extraction outside `data/source/` is a **development fixture/reference input**, not application memory.

Rules:

- runtime ingestion and rebuild commands must read from `data/source/`,
- pseudonymisation must rewrite the relevant content in `data/source/` to the stable per-person alias,
- a normal KEEPER rebuild must never silently re-import from the untouched fixture,
- the untouched fixture must remain gitignored and outside application persistence,
- tests may use isolated fixture copies, but production/runtime code must not use the untouched archive as a fallback source.

This distinction is required so:

```text
 pseudonymise person
→ verify
→ rebuild
→ verify again
```

cannot resurrect the original identity or lose the participant's evidence graph.

# 8. INGESTION RULES

Ingestion v1 performs mostly deterministic work.

Required:

1. enumerate source files,
2. parse document type,
3. preserve source metadata,
4. create Evidence Units,
5. identify obvious people and aliases,
6. populate `evidence_people`,
7. populate FTS,
8. generate embeddings,
9. validate record counts.

Optional later:

- topic tags,
- tentative stance,
- tentative claim summaries.

The entire query pipeline must work with **zero ingestion-time AI annotations**.

Never store an ingestion-time `AGREEMENT` as organizational truth.

## People detection and alias discovery

Prefer deterministic identity extraction from:

- transcript speaker labels,
- email sender/from headers,
- email addresses,
- clearly named participants,
- unique full-name mentions.

Aliases may include:

- full name,
- email,
- safe unique first/last-name variants,
- initials or nicknames only when corpus evidence strongly ties them to one person.

Before finalizing the `people` / `person_aliases` tables, run a **corpus-wide alias discovery pass**:

1. collect all explicit speaker/sender identities,
2. collect email addresses and display names,
3. scan for recurring short forms, initials, nicknames, and obvious spelling variants,
4. resolve only high-confidence aliases to an existing person,
5. leave ambiguous aliases unmerged.

This pass may use an LLM as a **candidate generator only**. Any alias mapping used for deletion must be stored explicitly and should be reviewable/debuggable.

Avoid broad fuzzy aliases that risk deleting unrelated text.

The deletion verifier is the final backstop for **tracked identifiers**: if a canonical name, known alias, known email, or deleted evidence ID survives anywhere in application-owned storage, deletion must fail rather than report success. This verifies all identifiers the system knows about; it does not prove that an undiscovered nickname never existed.

---


# 8.1 EMBEDDING INGESTION RESILIENCE

Embedding generation must not make Phase 1 unusable when credentials are absent or an API temporarily rate-limits/fails.

Requirements:

- batch embedding requests where the SDK supports batching,
- use bounded retries with exponential/backoff behavior for transient failures,
- provide an ingestion flag such as:

```text
--skip-embeddings
```

for parser/schema/FTS development without API access,

- unit tests must use a deterministic/mock embedding provider,
- run at least one real embedding integration smoke test when credentials are available,
- partial embedding failure must produce a clear ingestion warning/report rather than silently corrupting the Evidence Locker,
- do not claim semantic retrieval is ready until embedding rows exist for the intended corpus.

If `--skip-embeddings` is used:

- documents, Evidence Units, people/aliases, FTS, and all deterministic ingestion outputs must still succeed,
- Phase 1 can be structurally validated,
- Phase 2 semantic retrieval remains blocked until real embeddings are generated.


# 9. RETRIEVAL V1

## 9.1 Lexical retrieval

Use FTS5 and BM25 ranking.

Return approximately top 10–15 results.

## 9.2 Semantic retrieval

Store embeddings in SQLite.

At query time:

1. load the embedding matrix,
2. embed query,
3. compute NumPy cosine similarities,
4. return approximately top 10–15.

For this corpus size, an in-memory matrix is acceptable.

## 9.3 Rank fusion

Use deterministic Reciprocal Rank Fusion or similarly simple rank-based merging.

Do not introduce a learned reranker in MVP.

Example:

```text
RRF score = Σ 1 / (K + rank)
```

Choose a constant once and test retrieval quality; do not tune endlessly.

## 9.4 Context expansion

For each high-ranked unit, include appropriate neighboring evidence from the same document/thread.

Default transcript behavior:

- include the cited/high-ranked turn,
- include at least the immediately previous and next turn where available,
- dynamically expand to the smallest coherent conversational exchange when the cited turn is context-dependent.

Purpose: the LLM must not interpret isolated lines like “yes”, “sounds good”, or “let’s do that” without the proposal being accepted.

Do not over-expand until the context is the whole archive.

### Citation-context invariant

A technically valid evidence ID can still be semantically useless if its meaning depends on nearby turns.

Therefore:

- the **reasoner** receives neighbor-expanded context,
- the **validator** ensures the cited evidence ID is real and visible,
- the **UI evidence drawer** automatically renders the cited Evidence Unit plus nearby contextual units from the same thread/document, expanding beyond ±1 when needed to make the cited utterance understandable,
- the cited unit is visually highlighted,
- nearby context is clearly marked as context rather than as independently cited support.

Do **not** require the LLM to perfectly cite both sides of every conversational exchange. The backend/UI must make context inspectable deterministically.

## 9.5 Temporal sweep

When the query or Primary output concerns:

- current state,
- final decision,
- latest agreement,
- supersession,
- fulfillment,
- historical evolution,

perform a later-evidence sweep using the central topic/entity terms.

This is a retrieval operation, not a claim that newer = truer.

---

# 10. PRIMARY REASONER

Input:

- original question,
- retrieved evidence units,
- surrounding context,
- factual database metadata,
- optional tentative annotations if they exist.

The Primary Reasoner must output **structured candidate claims**, not prose-only answers.

## Allowed model outputs

The LLM may output:

- claim text,
- stance,
- claim confidence,
- supporting evidence IDs,
- conflicting evidence IDs,
- uncertainty,
- potential missing evidence,
- risk flags,
- topic/search terms,
- possible timeline events referencing evidence IDs.

## Forbidden model outputs as trusted provenance

Do not trust the LLM to provide:

- speaker,
- date,
- document name,
- thread title,
- exact quote.

The LLM should identify evidence by `evidence_id` only.

The backend hydrates all displayed citation metadata directly from the database.

This is mandatory.

---

# 11. RECEIPT SCHEMAS

Use Pydantic and strict enums.

Recommended conceptual schema:

```python
class Stance(str, Enum):
    PROPOSAL = "PROPOSAL"
    ASSUMPTION = "ASSUMPTION"
    OBJECTION = "OBJECTION"
    AGREEMENT = "AGREEMENT"
    COMMITMENT = "COMMITMENT"
    STATUS_UPDATE = "STATUS_UPDATE"
    IMPLEMENTATION_EVIDENCE = "IMPLEMENTATION_EVIDENCE"
    SUPERSEDED = "SUPERSEDED"
    UNCERTAIN = "UNCERTAIN"

class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class CaseStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class CandidateClaim(BaseModel):
    claim_text: str
    stance: Stance
    confidence: Confidence
    supporting_evidence_ids: list[str]
    conflicting_evidence_ids: list[str] = []
    uncertainty: str | None = None

class TimelineEvent(BaseModel):
    event_text: str
    state: Stance
    confidence: Confidence
    evidence_ids: list[str]

class CaseReceipt(BaseModel):
    query: str
    status: CaseStatus
    answer_summary: str
    claims: list[CandidateClaim]
    conflict_resolution: str | None = None
    timeline_events: list[TimelineEvent] = []
    missing_information: list[str] = []
    related_questions: list[str] = []
```

The final API may expose hydrated citations separately or return a hydrated UI schema after validation.

---

# 12. RISK ENGINE

The risk engine is mostly deterministic.

Do not trust the LLM’s self-confidence as the routing decision.

Force deep checking when the query or candidate claims involve concepts like:

- agreed,
- decided,
- approved,
- signed off,
- commitment,
- fulfilled,
- current,
- ultimately,
- superseded,
- who authorized/approved,
- assumption vs decision.

Also trigger deep checking when:

- stance is ambiguous,
- conflicting evidence exists,
- evidence spans materially different dates,
- later relevant evidence exists,
- source types disagree,
- confidence is MEDIUM/LOW,
- the answer requires authority inference,
- the answer requires commitment inference,
- the answer requires supersession/current-state inference,
- a status report conflicts with operational evidence,
- only one weak supporting source exists.

Do not implement a fake precise 0–100 risk formula merely for appearance.

A small, explainable ruleset is better.

---

# 13. SKEPTIC

The Skeptic exists only for medium/high-risk Cases.

It receives:

- question,
- candidate claims,
- supporting evidence IDs,
- important retrieved evidence.

Its task is **not** “give a second opinion.”

Its task is:

> Find evidence that would make the candidate answer wrong.

Process:

1. identify the weakest/highest-impact claim,
2. generate a small number of targeted counter-search bundles; **default maximum: 2** for MVP latency control,
3. each bundle should cover more than simple lexical negation,
4. run them through the same retrieval service,
5. inspect returned counterevidence,
6. output objections and counterevidence IDs.

For each important claim, the Skeptic should think across three counter-retrieval strategies:

### A. Direct contradiction
Search for explicit rejection, disagreement, cancellation, reversal, or non-approval.

### B. Alternative/replacement state
Search for later adoption of a competing technology, scope, plan, owner, or implementation state that would indirectly falsify the candidate.

Example:

Candidate:
`Kafka was chosen.`

Do not search only:
`Kafka rejected`.

Also search the same domain/topic for later architecture choices such as:
`RabbitMQ`, `streaming platform`, `message broker`, `replacement`, `migration`, or later implementation evidence.

### C. Later implementation / operational evidence
Search for what the organization actually implemented, shipped, escalated, deferred, or worked around after the supposed decision.

This catches cases where nobody says “X was reversed,” but later operational evidence shows Y became reality.

Additional adversarial intentions include:

- lack of confirmation,
- proposal-only language,
- operational behavior contradicting a status report,
- later implementation inconsistent with stated agreement,
- narrower scope than the candidate claim,
- superseding decisions expressed with different vocabulary.

The Skeptic must perform actual counter-retrieval. A prompt-only critique without new retrieval is insufficient.

Do not rely on naive string negation as the primary adversarial search method.

The two-bundle cap is an MVP default, not a proven optimum. Increase it only if evaluation shows a material recall improvement without unacceptable live-demo latency.

---

# 13.1 LATENCY BUDGET FOR HIGH-RISK QUERIES

High-risk reasoning is allowed to be slower than a trivial lookup, but it must remain demo-friendly.

Implementation guidance:

- default to at most **2** Skeptic counter-search bundles; increase only if evaluation shows materially better recall without unacceptable latency,
- keep each retrieval result set small,
- run independent retrieval work in parallel where straightforward,
- do not resend the entire archive,
- reuse embeddings / loaded matrices,
- avoid additional “polish” LLM calls,
- stream or expose coarse progress states in the UI such as:
  - `Analyzing evidence`
  - `Checking for contradictions`
  - `Reconciling current state`

Do not sacrifice attribution/currency correctness merely to achieve vanilla-RAG latency.

The performance target is not a hard SLA, but the architecture should aim for a high-risk response that feels like a deliberate audit rather than a stalled application.

---

# 14. FINAL RECONCILIATION

After Skeptic review, the Primary Reasoner gets:

- original question,
- initial claims,
- original evidence,
- Skeptic objections,
- new counterevidence.

It returns the final structured Receipt.

Rules:

- do not “average” contradictory claims,
- surface the conflict,
- explain why one interpretation is currently stronger,
- explicitly preserve uncertainty,
- return insufficient evidence when necessary,
- still explain what is known and what is missing.

The final answer must not pass through a new unconstrained “make it pretty” LLM stage.

---

# 15. DETERMINISTIC VALIDATOR

The validator runs after the LLM has completed reasoning and before any claim reaches the UI.

For every referenced evidence ID:

1. evidence exists,
2. evidence was present in the model-visible evidence set or in a documented retrieval result used during the Case,
3. evidence has not been deleted,
4. document exists,
5. source metadata is loaded from DB rather than model output.

For every important claim:

- at least one supporting evidence ID, unless the claim is explicitly an uncertainty/missing-information statement.

For every timeline event:

- at least one valid evidence ID.

If a model invents an evidence ID:

- reject it,
- do not render a fake citation.

Prefer failing a claim safely over showing unsupported provenance.

Hydrate displayed citation data from DB:

```text
evidence_id
document
date
speaker/sender
thread context
raw_text
```

The model cannot override these fields.

---

# 16. DECISION EVOLUTION — PRIMARY STANDOUT FEATURE

Decision Evolution is core, not a stretch feature.

Purpose:

Show how evidence-supported organizational state changed over time.

Example:

```text
SEP 2024
PROPOSED
EV-117
   ↓
JAN 2025
POSSIBLE AGREEMENT
EV-288
   ↓
NOV 2025
CONTRADICTED
EV-551
   ↓
FEB 2026
SUPERSEDED
EV-702

CURRENT:
Separate partner track
```

Rules:

- every node must have evidence,
- ambiguous transitions stay ambiguous,
- never invent missing transitions to make a smooth story,
- timeline ordering is chronological,
- “current” is a reasoned conclusion, not merely the newest statement,
- every node is clickable to original evidence.

Generation should reuse retrieved/temporally expanded evidence. Avoid adding a separate giant temporal architecture.

---

# 17. PROJECT PULSE — OPTIONAL AFTER CORE

Do not build Project Pulse until:

- ingestion works,
- retrieval benchmark is acceptable,
- Primary Reasoner works,
- validator works,
- Skeptic works,
- deletion works,
- Decision Evolution works,
- core UI works.

If implemented, limit v1 to:

- possible contradiction,
- possible unresolved commitment,
- possibly stale/superseded decision.

Reconsideration Radar is a separate Phase 7 innovation extension, not a
replacement for the frozen core and not a reason to delay the Phase 1 review or
the Phase 2–6 exits. It must surface only previously rejected/deferred ideas
whose original blocker and a possible changed condition are both evidence-
backed. It must distinguish internal evidence, external signals, bounded
assessment, and missing information, and may say only `worth reassessing` — not
that the organization should pursue the idea. The design and exit criteria are
in `docs/RECONSIDERATION_RADAR.md`.

Each Pulse finding must link to a validated Case.

Dependency:

```text
Pulse Finding
    ↓
Case
    ↓
Receipt
    ↓
Evidence
```

Do not render free-floating AI findings with no validated Case/evidence.

Precompute Pulse findings. Do not run expensive full-archive audit on every page load.

---

# 18. PERSONAL DATA PSEUDONYMISATION, PROFILES, AND REVERSAL

## 18.0 Architecture v1.6 pseudonymisation contract — normative

The operation is robust pseudonymisation, not generic deletion or irreversible anonymisation. This subsection is the implementation contract. The v1.5 material after the divider below is historical only and must not be implemented.

### 18.0.1 Identity state and identifiers

Every participant has a durable public row:

```yaml
subject_id: random internal UUID
display_alias: Participant Q7M4-N8
privacy_state: ACTIVE | PSEUDONYMISED
```

- `subject_id` is generated with a cryptographically secure random UUID and contains no name-derived material. It is the relational key for profiles, evidence relationships, cases, and API routes.
- `display_alias` is generated independently with cryptographically secure randomness, is unique and stable, and is never derived from a name, name hash, initials, employee number, job title, or predictable sequence. Collision handling retries generation.
- `Participant Q7M4-N8` is an example display format, not a derivation algorithm.
- `ACTIVE` profiles may expose the real name and allowed metadata. On pseudonymisation, the public row loses the original name and direct identifiers, changes to `PSEUDONYMISED`, and retains only the stable alias plus non-identifying metadata needed for organizational context.
- The participant row is never deleted. `evidence_people` rows are never cascade-deleted. Pseudonymisation preserves every Evidence Unit, Evidence ID, locator, relation (`AUTHOR`, `SPEAKER`, `MENTIONED`), and complete profile history.
- Pseudonymised records remain personal data. Do not claim irreversible anonymisation, cryptographic erasure, or universal legal/GDPR compliance.

### 18.0.2 Universal clickable profile

Every participant is a clickable profile target from speaker/sender labels, mentions, citations, timeline nodes, and the people list.

- An active profile shows the real name and permitted metadata.
- A pseudonymised profile shows only `display_alias` and non-PII status/count fields. It must not reveal the original name, email, employee ID, title, or vault state details.
- Both states show the participant's entire history: all linked chat logs, emails, meeting transcripts, source metadata, and the exact contribution/quote for every Evidence Unit in which the subject is an author, speaker, or mentioned participant.
- History is hydrated from the public relational graph and sanitized evidence rows. It never requires a vault lookup and never reconstructs identity from search results.
- The alias must remain distinct per participant so the profile graph does not collapse different people into one generic label.

### 18.0.3 Isolated reversal vault

The original identity mapping is a separate security boundary, not a normal table in `data/app.db`.

- Store `subject_id -> encrypted original identity bundle` in a separate encrypted vault database/file owned only by a dedicated vault repository. Do not put a vault table in `data/app.db`; a normal SQLite connection must have no path to the vault. The bundle may contain the original name, original email/aliases, and the metadata required for an explicit reversal.
- Encrypt the bundle with authenticated encryption. The key is supplied through a dedicated secret/key-management boundary and is never stored beside the main database, source archive, FTS index, embeddings, cache, or logs. Store only ciphertext, nonce/IV, key version, subject ID, and vault timestamps.
- Ordinary repositories and endpoints must not open, attach, join, search, export, embed, cache, or log vault plaintext. There must be no fallback query that tries to resolve a pseudonym through the vault.
- The public `privacy_operations` audit record contains only operation ID, subject ID, display alias, from/to state, pseudonymised timestamp, counts/status, and verification result. It never contains the original name or email.
- A normal anonymous profile, global search, evidence API, case API, or reasoning trace must be unable to look up the original identity. Only the separately authenticated and authorized “Reverse Pseudonymisation” admin workflow may decrypt the vault record.

### 18.0.4 Alias-bearing canonical source and derived data

Reuse the existing role-aware redaction coverage, but replace every target-specific generic marker with that participant's stable `display_alias`.

The application-owned canonical source must rewrite the target in all applicable locations: transcript speaker lines, email/report sender headers, sender addresses, recipients, attendee lists, signatures, subject/meeting context, inline mentions, handles, employee/operator identifiers, and other direct identifying metadata. Preserve the surrounding organizational facts and exact contribution text wherever possible. Do not delete a whole Evidence Unit merely because it contains the target; the target's history and quote must remain inspectable under the alias.

The rewritten source is still application-owned personal data. FTS, embeddings, caches, receipts, Cases, timeline events, Radar/Pulse findings, and exported artifacts must be regenerated or invalidated from the alias-bearing source. Old text and old embeddings must not survive the operation.

Generic `[REDACTED PERSON]`, `[REDACTED SPEAKER]`, and `[REDACTED SENDER]` markers are retired for participants. Native anonymous labels such as `Me`, `Them`, and `Guest 1` remain anonymous source labels and must not be conflated with pseudonymised subjects.

### 18.0.5 Staged pseudonymisation sequence

```text
authenticate request and acquire exclusive privacy/read-write gate
    ↓
resolve ACTIVE subject_id and compute affected files/evidence/dependencies
    ↓
generate or load stable display_alias; write encrypted vault record
    ↓
durably write a crash-resumable plan containing IDs, paths, alias, and counts only
    ↓
atomically rewrite canonical source and structural metadata to the alias
    ↓
transactionally update public people/profile rows and scrub original aliases
    ↓
preserve evidence_people and Evidence IDs; invalidate Cases/findings/FTS/embeddings
    ↓
checkpoint/VACUUM/clear owned caches and regenerate public derived data
    ↓
verify zero original identifiers on every public application surface
    ↓
record PSEUDONYMISED, pseudonymised_at, operation ID, and verification result
    ↓
remove the temporary plan and release the gate only after verification passes
```

The plan may contain `subject_id`, Evidence IDs, document IDs, source locators, replacement alias, paths, and counts. It must never contain the original name, original email, unsanitized source text, or a reversible alias-to-name mapping. A crash leaves the application privacy-locked; recovery resumes by recorded state and never guesses.

### 18.0.6 Verification and rebuild invariants

Verification must scan the canonical source, public database text/metadata, FTS, caches, Cases/receipts, timeline/Radar/Pulse artifacts, operation plans, and logs for original names, emails, tracked aliases, and unsanitized direct identifiers. It must also verify that:

- the public subject row is `PSEUDONYMISED` with the expected stable alias;
- no public alias table contains the original identifiers;
- the original identity exists only as encrypted vault ciphertext;
- every pre-operation `evidence_people` relationship remains present;
- every linked Evidence Unit remains profile-readable with the alias and exact sanitized quote;
- old embeddings and stale derived artifacts are gone, and new representations were built from alias-bearing text;
- a full rebuild from `data/source/` cannot resurrect the original identity or lose the participant graph.

Do not report success if any check fails. This is application-level pseudonymisation verification, not a mathematical proof against unknown external copies.

### 18.0.7 Explicit reversal workflow

“Reverse Pseudonymisation” is a separately authenticated, role-gated admin operation. It is not exposed through standard profile/search/evidence APIs and is never available merely because a caller knows `subject_id` or `display_alias`.

The workflow decrypts the vault record only inside the dedicated vault service, authorizes the request, atomically rewrites the public canonical source and derived representations back to the active identity, restores active profile metadata, records an ID/status-only audit event, and verifies completion. It must not print the original name to ordinary logs or leave plaintext in the operation plan. Re-pseudonymisation reuses the stored stable alias unless an explicit, separately audited rotation is required.

---

## 18.99 Historical v1.5 material — non-binding; do not implement

The following old sections describe generic irreversible markers, name-derived IDs, locator revocation, and whole-unit deletion. They are preserved only so earlier review documents remain understandable. Architecture v1.6 above supersedes every requirement below. The old `app/privacy/` implementation is to be replaced, not incrementally debugged into this contract.

## 18.1 Deletion target expansion

When deleting person P, resolve the full deletion target, where applicable:

- canonical name,
- verified full-name variants,
- reviewed aliases (section 0.1's identity-hardening manifest),
- email addresses,
- explicitly reviewed initials or nicknames,
- employee/account/operator identifiers,
- identifying speaker/sender metadata,
- identifying source headers (From/Von/Från, Attendees, Subject/Meeting context — section 18.1.1),
- unique identifying contextual phrases when explicitly recognized.

Do not authorize fuzzy deletion based solely on capitalization, substring matching, uniqueness, or an LLM guess. The hardened identity/alias rules (section 0.1: a capitalized free-text span is never auto-promoted to `people`; short-form aliases require an explicit reviewed manifest entry) are a prerequisite for safe deletion and must not be weakened to make deletion easier.

Find every Evidence Unit where P is AUTHOR, SPEAKER, or MENTIONED. For each one (section 18.6 has the full sequence):

1. attempt targeted redaction of P's verified identifying spans and metadata,
2. evaluate whether P remains reasonably identifiable from what's left,
3. if necessary, redact a larger span,
4. delete the full unit only when adequate anonymization cannot otherwise be achieved.

There is no unconditional rule that every authored/spoken unit is deleted, that every mentioned-only unit is preserved, or that every occurrence of an ambiguous first name is redacted — each is evaluated by the same identifiability test. A statement such as “Kwame told me the extraction succeeded” is, by default, **redacted** (P's name replaced with the reserved `[REDACTED PERSON]` marker — section 18.7) rather than deleted outright, because the fact that an extraction succeeded is non-personal organizational evidence that does not depend on knowing who was told. Whole-unit deletion remains available, and is used, whenever redaction would leave P reasonably identifiable or would not adequately protect P's data.

Fine ingestion granularity remains necessary — now for two reasons instead of one: it keeps redaction spans small and precise, and it minimizes collateral loss on the escalation path when whole-unit deletion is still required:

- transcript unit → normally one speaker turn,
- email unit → one message,
- report unit → one bullet / short factual sub-paragraph where possible.

The parser must avoid coarse units that bundle unrelated facts, because both redaction and the whole-unit-deletion fallback should not create unnecessary organizational amnesia.

## 18.1.1 Canonical source and rebuild safety

A purge/anonymization is incomplete if a later rebuild can silently resurrect deleted or de-anonymized data.

Sanitization of the app-owned canonical source (`data/source/`) covers more than `evidence_units.raw_text`. Where applicable it must also cover:

- email/report `From`, `Von`, or `Från` header values,
- sender email addresses,
- transcript speaker-marker lines,
- bare speaker-name and initials UI chrome,
- transcript `Attendees` headers,
- `Subject`, `Meeting`, and other document-level context fields,
- signatures,
- inline mentions,
- the reviewed identity manifest (`data/source/reviewed_identities.json`) entry for the deleted/anonymized person,
- any other structural value that ingestion discards while parsing but that still physically exists in `data/source/`.

Note that `speaker_email` is a transient `ParsedUnit` field produced by the email/report parsers, not an `evidence_units` database column; its normal persistent representation is the person's EMAIL alias, while the literal address can still remain in canonical-source headers or body text and must be sanitized there directly.

Therefore:

- the app-owned canonical source used for rebuilds must itself be sanitized during deletion, across the full scope above,
- any app-owned normalized manifests/copies must be sanitized too,
- rebuild scripts must read only from the sanitized canonical source or sanitized manifest,
- no hidden unsanitized backup may remain inside application-owned runtime/storage directories.

If the original hackathon corpus is treated as external/read-only input outside KEEPER's owned persistent state, keep that boundary explicit in code and documentation. Do not copy an untouched version into app-owned storage and later rebuild from it after deletion.

A successful purge/anonymization must preserve this invariant:

> running the normal rebuild command after deletion must not resurrect the deleted person's data, and a sanitized surviving unit must re-ingest as sanitized, not fail to parse or silently drop its content (section 18.7).

**Git-history boundary.** `data/source/` is tracked by Git, so sanitizing the working tree does not erase the pre-sanitization content from `.git`'s object history. Therefore:

- the running application and the normal rebuild process use only the current sanitized `data/source/` working tree — they never read from `.git` history,
- `.git` object history and the remote challenge repository are development/distribution records, not runtime application persistence, and are never a runtime rebuild source,
- this challenge implementation does not claim to erase remote Git history or provide universal legal erasure from third-party/version-control systems,
- do not create new runtime backups from Git history after a deletion/anonymization operation.

---

## 18.2 Dependency invalidation

Before deleting evidence, identify dependent:

- Cases,
- timeline events,
- Pulse findings.

Use the relational reference tables, not a graph database.

## 18.3 Canonical rebuild source invariant

A purge is incomplete if an untouched app-owned source copy can later recreate the deleted person during `rebuild`.

Therefore:

- the canonical source representation used by KEEPER rebuilds must itself be sanitized,
- rebuild scripts must never read from an unsanitized retained copy inside application-owned storage,
- no hidden backup of the imported corpus may remain under `data/`, cache directories, temp export folders, or debug artifacts,
- if the original hackathon corpus is treated as external/read-only input outside KEEPER’s owned persistent state, document that trust boundary explicitly and ensure production rebuilds use only the sanitized application-owned canonical source.

A successful deletion must remain deleted after a full rebuild.

## 18.4 Physical purge/anonymization sequence

Implement a transactional/safe sequence. Per section 18.6, each affected Evidence Unit is independently classified as ANONYMIZE (redact and keep) or DELETE (remove in full); the sequence below applies to both, substituting "sanitize source span(s) + update surviving fingerprint(s)" for ANONYMIZE units and "scrub source span(s) + revoke locator(s)" for DELETE units at the marked step. Sections 18.10–18.12 give the full staged/locked/crash-safe version of this sequence; this is the logical shape it follows:

```text
resolve person + full deletion target (section 18.1)
    ↓
identify target evidence IDs and classify each ANONYMIZE or DELETE (section 18.6)
    ↓
identify dependent Cases/findings
    ↓
physically scrub (DELETE units) or sanitize (ANONYMIZE units) corresponding source
content under app control, including structural metadata (section 18.1.1) and the
person's reviewed-identity manifest entry — `data/source/reviewed_identities.json`
is a source JSON file, not a database row, so it is sanitized here alongside the
other source-file edits, never inside the SQLite transaction below
    ↓
one SQLite transaction (no filesystem mutation and no external API/model call
inside it):
    UPDATE evidence_units.raw_text for sanitized surviving (ANONYMIZE) units
    UPDATE evidence_units.speaker_sender to the reserved marker where the
        target's own attribution is cleared/replaced (section 18.7)
    UPDATE evidence_units.thread_context for sanitized surviving units where
        it identified the target
    UPDATE documents.title / documents.thread_context where they identified
        the target
    DELETE evidence_units rows for DELETE units
    DELETE the target's people / person_aliases / evidence_people rows, using
        verified cascade behavior where the schema's ON DELETE CASCADE
        already covers it
    UPDATE source_locators.content_fingerprint for surviving constituents
        (section 18.8)
    revoke (never delete) source_locators rows for every constituent locator
        of a fully deleted unit, including every constituent of a merged
        transcript unit (section 18.8)
    DELETE old FTS rows and insert sanitized FTS rows for survivors
    DELETE old embedding rows for every touched evidence_id (ANONYMIZE and
        DELETE alike)
    DELETE/invalidate dependent Cases, receipts, timeline events, and Pulse
        findings, and their reference rows (case_evidence, finding_evidence)
commit
    ↓
clear relevant runtime caches/artifacts
    ↓
checkpoint/truncate SQLite WAL or journal state as applicable
    ↓
VACUUM SQLite
    ↓
close/reopen database and verify auxiliary DB files
    ↓
regenerate embeddings for sanitized survivors, only now and only while the
privacy lock still blocks queries (section 18.12) — never inside the
transaction above, and never by calling an external provider while holding
a database transaction open
    ↓
rebuild retrieval representations as needed
    ↓
recompute active affected Case from surviving evidence
    ↓
run deletion/anonymization verifier (section 18.5)
```

Do not keep a hidden personal-data backup inside `data/`.

If an external original file outside application control exists, document that it is external input, not retained internal state. All application-owned copies must be purged or sanitized.

Embedding regeneration for sanitized survivors requires the organizer GPT embedding provider. If it is unavailable or regeneration fails, leave the affected embedding rows absent and report semantic retrieval as degraded/pending for those units — privacy completion must not depend on network availability, and an old embedding for changed or deleted text must never be retained. The same applies to recomputing dependent Cases/receipts/timelines/Pulse findings that require the external reasoning model: invalidate or remove the obsolete persisted output inside the local transaction; recomputation that needs the external model happens afterward, while still locked; if it fails, the obsolete result stays absent — it is never left in place or silently restored.

## 18.4.1 SQLite physical-cleanup details

Row deletion or update alone is not enough to claim application-level physical purge: a logical `UPDATE`/`DELETE` does not guarantee the prior bytes are absent from auxiliary pages. SQLite may retain recently changed/deleted bytes in:

- the main database file (freed B-tree pages until compacted),
- `-wal`,
- `-shm`,
- rollback journal/temp files,
- application caches.

Implementation must account for the configured journal mode (WAL is currently enabled — `backend/app/db/connection.py`).

At purge/anonymization time, for every operation that changes or removes personal data (this applies equally to whole-unit deletion and to in-place redaction of a surviving unit):

1. enable appropriate SQLite secure-deletion behavior before the sensitive UPDATE/DELETE,
2. complete the transactional logical mutation (commit),
3. checkpoint/truncate WAL if WAL mode is enabled,
4. run `VACUUM` when required by the chosen approach,
5. close and reopen the database,
6. verify the main DB and relevant auxiliary/cache artifacts for tracked identifiers and deleted evidence IDs.

Do not report deletion/anonymization success while a stale WAL/journal/cache still contains tracked deleted data, or while verification (step 6) has not passed — fail closed instead.

Do not persist a redacted row's prior content fingerprint anywhere (including a recovery/staging plan) merely to have something to byte-scan for later — storing the old fingerprint would itself preserve the derived value the operation is supposed to remove. Overwrite it as part of step 2, perform the physical cleanup above, and verify by checking the current logical/tombstone state plus tracked direct identifiers (canonical name, aliases, emails, deleted evidence IDs), not by re-deriving and searching for a value that should no longer exist anywhere.

This sequence verifies tracked identifiers and known application-owned representations. It is a strong application-level check over what the system knows and owns, not a generic byte-scan proof that anonymization is universally complete against every conceivable indirect encoding.

---

## 18.4.2 Logging

Deletion logs may contain:

- deletion request ID,
- timestamp,
- counts of removed evidence units,
- counts of invalidated Cases,
- verification status.

Deletion logs must **not** contain:

- the deleted person’s name,
- deleted email,
- raw deleted text,
- deleted evidence body.

Avoid persisted raw LLM prompts/responses globally. They complicate deletion.

## 18.5 Verification

Deletion/anonymization is not “successful” until a verifier checks:

- source files under app control (including the structural scope in section 18.1.1, not only unit body text),
- database text fields,
- aliases,
- FTS,
- cached JSON,
- Case JSON,
- Pulse JSON,
- runtime artifacts,
- `data/privacy_ops/` (section 18.10's operation-plan directory),

for:

- target canonical name,
- aliases/emails,
- deleted evidence IDs (for units that were fully deleted).

Expected result for all **tracked identifiers and references, on every permanent application surface**:

```text
0 surviving matches for canonical name / known aliases / known emails
0 deleted evidence references
0 surviving embedding rows for deleted evidence
0 stale references in Cases / timelines / Pulse / caches
0 leftover data/privacy_ops/ staging artifacts for a completed operation
```

This is a strong application-level verification over what the system knows and owns. Do not describe it as a mathematical proof that no unknown alias or indirect reference could exist, and do not describe the SQLite-level check (section 18.4.1) as a generic byte-scan proof of universal anonymization.

**Revoked-locator tombstones are not evidence resurrection.** The zero-surviving-matches result above — "0 deleted evidence references" and the rest — applies to application evidence: `evidence_units`, FTS, embeddings, Cases, receipts, timelines, Pulse findings, caches, and other persisted artifacts. A revoked `source_locators` row (section 18.8) is intentionally retained; its whole purpose is to prevent the deleted locator/position from ever being reassigned. Its continued presence is not evidence resurrection and must not, by itself, cause the verifier to fail. What the verifier does require of that row is that it contain neither the original content fingerprint nor any direct identifier — only `revoked_at` set and the sentinel value in place of the fingerprint (section 18.8).

**Sequencing while an operation is still active (sections 18.10–18.11).** The zero-surviving-matches rule above applies to every *permanent* application surface. It does not apply, for the brief in-flight window of a single operation, to the operation's own temporary plan file, which is allowed to contain a small, explicitly bounded set of fields (section 18.11) and is itself schema-validated rather than scanned for zero matches. The verifier runs in two passes:

1. **Pre-finalization verification** checks every permanent surface above (excluding the plan file itself) for zero tracked matches.
2. Once pre-finalization verification passes, transition the operation's lock state to `FINALIZING`, delete the staging plan file, and run a **final scan** confirming `data/privacy_ops/` itself now contains no target-bearing artifact at all. Only then release the privacy-operation lock (section 18.10).

If the process crashes after the plan file is removed but before the lock is released, startup recognizes the `FINALIZING` state from the lock record, repeats the final scan/cleanup, and releases the lock — a missing plan file is the expected shape of that state, not corruption to fail on.

Then rerun an affected Case and show the new result.

Use accurate wording:

> application-level physical purge/anonymization with dependency invalidation and post-deletion verification

Do **not** claim cryptographic erasure, and do not claim universal legal or GDPR compliance — this is the project's own judge-confirmed deletion/anonymization requirement.

## 18.6 Relation-symmetric redaction policy

For every Evidence Unit where the target person P is AUTHOR, SPEAKER, or MENTIONED, apply the same sequence — there is no relation-based shortcut:

1. attempt targeted redaction of P's verified identifying spans and metadata within the unit,
2. evaluate whether P remains reasonably identifiable from the unit as redacted (considering the redacted unit's own content plus any structural metadata that survived — e.g. an unredacted seat/attendee count, a still-present unique role description),
3. if P remains identifiable, redact a larger span (up to the whole unit's text),
4. delete the full unit only when adequate anonymization cannot otherwise be achieved.

Forbidden unconditional rules:

- every unit where P is AUTHOR or SPEAKER is deleted by default,
- every unit where P is only MENTIONED is preserved by default,
- every occurrence of an ambiguous first name is redacted by default (an ambiguous name may belong to someone other than P; redacting it without the identity-hardening manifest's confirmation risks over-redaction of an unrelated person's evidence).

For mentioned-only evidence in particular: preserve the other participant's own attribution and unrelated content in the same unit unless the unit as a whole must be removed as the final fallback. Reasoning over a marker-containing unit must not automatically discount every fact in it equally — only the attribution or claims that actually depended on the redacted portion are weakened; unrelated facts in the same unit keep their original evidentiary weight.

## 18.7 Reserved redaction markers

Three role-aware markers stand in for a redacted person's identity in sanitized canonical-source content:

- `[REDACTED PERSON]` — inline text redaction (a mention, a name inside body text),
- `[REDACTED SPEAKER]` — a transcript speaker-marker/attribution replacement,
- `[REDACTED SENDER]` — an email/report `From`/`Von`/`Från` display-name replacement.

Contract:

- these markers are irreversible and generic — nothing in application-owned storage maps a marker back to the specific person it replaced,
- markers are not people, not aliases, and not deletion targets; they must never be written to `people.canonical_name` or `person_aliases.alias`,
- parsers, people/identity discovery, relation linking, and mention detection must treat a reserved marker as a reserved anonymous value — never as a new structural person, never as a candidate full-name/alias match, and never as a mentionable identity. This extends the same treatment the parsers already give the existing anonymous labels (`Me`, `Them`, `Unknown Speaker`); a reserved marker must be added to that same exclusion set everywhere it is checked, not introduced as a second, differently-handled case,
- a Teams-format `[REDACTED SPEAKER]` marker line, and a redacted `From`/`Von`/`Från` header, must both remain parseable by the normal parser after a rebuild — a redacted turn or message must still be recognized as its own attributable (if anonymous) unit, not silently dropped as unparseable chrome or merged into a neighboring unit,
- `is_anonymized` is **not** added to the contract as a required schema field. `evidence_units` is a rebuildable table (rebuilt from `data/source/` on every ingest), so a bare boolean column cannot be a durable signal by itself; the marker string baked into the sanitized canonical source is itself the durable signal and survives rebuild for free.

## 18.8 Stable Evidence IDs under redaction, and locator revocation

A unit that is redacted rather than deleted keeps its existing Evidence ID; only its content changes.

A unit that is deleted in full must have its locator identity permanently retired, never reassigned or silently resurrected:

- `source_locators` rows for a fully deleted unit are never removed with `DELETE`. They are **revoked in place**: a future nullable `revoked_at` timestamp is set, and the prior `content_fingerprint` is overwritten with a fixed non-fingerprint sentinel value,
- revoked rows are excluded from normal fingerprint matching during ingestion,
- a collision between a freshly computed natural locator (e.g. a transcript timestamp or a date-slug) and an existing **revoked** row must fail loudly rather than silently reuse or resurrect it,
- before revocation, a `source_locators` row legitimately contains a fingerprint *derived from* the original unit's content — do not claim the row "never contained personal data." The accurate statement is: after the fingerprint is overwritten with the sentinel and the SQLite physical-cleanup sequence (section 18.4.1) completes, the row retains no original fingerprint or direct personal identifier.

**Migration checkpoint:** `source_locators` is a persistent table (section 7.3), never dropped/recreated by rebuild. The repository includes a guarded `PRAGMA table_info` / `ALTER TABLE ... ADD COLUMN` migration for `revoked_at`, because `CREATE TABLE IF NOT EXISTS` cannot add the column to an existing table. That migration and the locator-revocation primitive are only groundwork; the future privacy service must decide when to revoke all affected locators as part of a full deletion operation.

**Merged transcript constituents.** A final transcript Evidence Unit may be the result of merging several consecutive same-speaker pre-merge fragments (section 8's transcript merge behavior), and its evidence_id exposes only the **first** constituent fragment's locator — the other constituent fragments were each independently assigned their own locator during parsing, but only the first is ever surfaced. Do not describe an Evidence Unit as if it always maps to exactly one source locator or one contiguous source line. A future deletion/redaction implementation acting on a merged unit must:

- replay-resolve every fragment in the document (section 18.9),
- reconstruct the exact merge group the original ingestion would have formed,
- sanitize every constituent fragment's own source range, not only the first,
- update every surviving constituent's own fingerprint when the merged unit is anonymized,
- revoke every constituent's locator, not only the first, when the merged unit is fully deleted.

## 18.9 Pure replay and the source-span model

Locating exactly which bytes in `data/source/` correspond to a given evidence_id requires re-deriving the mapping from the current file, because the mapping from merge groups and report sub-line spans to locators is recomputed at ingestion time and is not separately persisted (section 18.8). Privacy planning must do this **without** mutating anything:

- the ordinary ingestion-time locator-assignment functions may create new `source_locators` rows when nothing matches; they must not be called for privacy planning, because planning must never mint a locator,
- a privacy-planning replay resolver returns an existing assignment or fails — it never mints one,
- an unmatched live fragment encountered during replay (the current file doesn't produce the assignment the manifest expects) is an integrity error requiring operator review, not a reason to invent a new locator or silently skip the fragment.

**Source-span model.** Do not assume every unit corresponds to one contiguous line or one numbered bullet. A unit's source footprint must be represented generally enough to cover:

- multiple whole lines (a plain multiline paragraph in a report, or a transcript fragment's chrome plus content lines),
- a column range within a single line (a report section header's inline trailing text, which shares its line with the header label),
- multiple constituent fragments belonging to one merged transcript unit (section 18.8).

Report units in particular may take any of these shapes, not only "one bullet = one line": a multiline plain paragraph with no recognized section header; inline status text embedded in a section-header line; a header paragraph with zero or one bullets, whose content is combined with other lines into one unit; or one standalone bullet line in a section with two or more bullets. The replay/span model must handle all of these, not only the last.

## 18.10 Privacy-operation safety

A deletion/anonymization request is a staged, exclusive operation, not an in-request side effect:

1. acquire one exclusive privacy-operation lock before any mutation,
2. while the lock is held, block normal query serving and ingestion — source and the database may temporarily disagree mid-operation, and nothing should read that inconsistent state,
3. compute and durably write the full operation plan before touching source or database content,
4. update the plan file and the lock's own state through atomic same-directory file replacement (write a new temp file, then rename over the old one) — never append to it, since an append that's interrupted mid-write can corrupt the file's structure,
5. atomically replace each touched source file the same way,
6. commit the logical SQLite changes in the transaction described in section 18.4,
7. perform the SQLite physical cleanup (section 18.4.1),
8. verify (section 18.5),
9. remove the operation's plan/state,
10. release the lock last, only after verification has fully passed.

Application startup must check for an unfinished privacy operation (the lock present) and resolve it — resuming from wherever it left off, per its recorded state — **before** serving any normal request or ingestion.

**Recovery by recorded state.** Startup resolves an unfinished operation according to its recorded lock/plan state, not by guessing:

- `PLANNING` with no plan file, and verification confirming no source or database mutation actually began: the orphan lock may be cleared safely, without running the rest of the recovery sequence,
- any resumable state with a valid, readable plan (from `SOURCE_IN_PROGRESS` through `SQLITE_CLEANUP_DONE`/`VERIFIED`): resume automatically from the earliest recorded incomplete step forward,
- `FINALIZING` with no plan file (the plan was already removed but the lock was not yet released): repeat the final cleanup/verification scan, and release the lock if it succeeds,
- any other combination — a lock without a plan outside the two cases above, or a plan/lock that is unreadable, malformed, or otherwise inconsistent — fails closed for operator review rather than guessing how to resume.

A privacy operation that fails at any stage must leave the application locked, not silently unlocked, and must never report deletion/anonymization success.

## 18.11 Staging-data accuracy

Do not claim the active operation plan (section 18.10) contains no personal data — that claim would be false and must not be made without proving it.

The plan **may** temporarily contain:

- the name-derived `person_id` (the existing `people.person_id` is a slugified canonical name, e.g. `ahmed-nasser` — this is a minimal, lightly-encoded personal identifier, not an opaque token, and the plan legitimately needs it to make the database step resumable after a crash),
- Evidence IDs,
- document IDs,
- locators,
- already-sanitized replacement content.

The plan **must not** contain:

- the canonical name as a separate field, unless strictly required,
- aliases or email values,
- original unsanitized raw text,
- a reversible mapping from a redaction marker back to the target person.

Treat the plan as temporary protected personal data with a minimal lifetime: it lives only for the duration of one operation, it is stored under the same access restrictions as any other application-owned personal-data surface, and its removal is a required step (section 18.10, step 9) verified by the final scan (section 18.5) before the lock is released.

## 18.12 Embeddings and dependent results under privacy operations

Deleting the old embedding rows for every touched evidence_id happens inside the local database transaction (section 18.4) — this is a local DELETE, not a network call, and must not be skipped or deferred.

Regenerating an embedding for a sanitized survivor is a separate, later, optional step: it happens only after the privacy-sensitive transaction has committed, only while the privacy lock (section 18.10) still blocks normal queries, and it must never run inside that transaction or hold it open while waiting on an external provider. If the organizer GPT embedding provider is unavailable or regeneration fails, the affected rows are left absent and reported as degraded/pending semantic retrieval — privacy completion must never depend on network availability, and an old embedding for changed or deleted text must never be left in place.

The same pattern applies to dependent Cases, receipts, timeline events, and Pulse findings: invalidate or remove the obsolete persisted output inside the local transaction; any recomputation that requires the external reasoning model happens afterward, while still locked. If that recomputation fails, the obsolete result stays removed — it is never restored just because recomputation didn't succeed.

---

# 19. PRODUCT SURFACES

Guaranteed MVP surfaces:

## A. Ask KEEPER

Natural-language question entry.

It opens/creates a Case. It is not a normal chat bubble stream.

## B. Case View

Display:

- answer/ruling,
- status,
- claim confidence,
- support,
- conflicts,
- conflict resolution,
- uncertainty,
- missing information,
- Decision Evolution,
- source receipts.

For transcript/email evidence, opening a receipt must show:

- the cited Evidence Unit highlighted,
- at least ±1 adjacent conversational units when available,
- the surrounding meeting/email/thread identity,
- a visual distinction between the cited unit and contextual neighbors.

A receipt must be understandable to a judge without requiring them to infer what an isolated “yes” or “sounds good” referred to.

## C. Decision Evolution

Primary “wow” feature.

Clickable timeline nodes open evidence.

## D. Universal Participant Profiles and Privacy Console

Every participant is clickable from a speaker, sender, mention, citation, timeline node, or privacy list. The profile pop-up must show:

- ACTIVE participant: real name and allowed metadata;
- PSEUDONYMISED participant: `display_alias` and no original name, email, employee ID, title, or other PII;
- everyone: the complete DB-hydrated history of chat logs, emails, meeting transcripts, and the participant's specific contributions/quotes linked to their Evidence Units.

The Privacy Console previews and runs pseudonymisation, displays the stable alias and verification result, preserves the relationship graph, and shows post-operation recalculation. Reversal is not a normal profile action; it is an authenticated admin workflow backed by the isolated vault.

## E. Project Pulse

Optional/stretch only.

---

# 20. API CONTRACT

Keep APIs narrow and typed.

Recommended endpoints:

```text
POST /api/cases/query
GET  /api/cases/{case_id}
GET  /api/evidence/{evidence_id}

GET  /api/privacy/people
POST /api/privacy/preview
POST /api/privacy/pseudonymise
GET  /api/people/{subject_id}
GET  /api/people/{subject_id}/history

GET  /api/health
```

Optional:

```text
GET /api/pulse
```

`POST /api/cases/query` returns a validated Case object, not arbitrary Markdown.

`GET /api/evidence/{evidence_id}` returns exact DB-hydrated source metadata/text.

The pseudonymisation endpoint returns counts, `subject_id`, `display_alias`, state, operation ID, and verification result — never the original identity. Profile/history endpoints are DB-hydrated and must not access the reversal vault. A separate admin-only reverse endpoint is outside the standard API surface and requires explicit authorization.

---

# 21. FRONTEND RULES

The UI must not become a source of hallucination.

Frontend renders validated API fields.

Do not ask an LLM to rewrite the final Receipt into new prose.

Case layout priority:

1. conclusion/status,
2. confidence/uncertainty,
3. supporting evidence,
4. conflict evidence,
5. conflict-resolution explanation,
6. Decision Evolution,
7. raw evidence drawer.

Make provenance easy to inspect in one click.

Use clear status labels. Avoid decorative complexity.

---

# 22. ERROR HANDLING

Fail safely.

Examples:

- LLM JSON invalid → bounded retry using same structured schema, then return controlled error.
- Organizer GPT service unavailable → API returns explicit temporary analysis failure, not fabricated answer.
- fabricated evidence ID → drop/reject claim.
- retrieval returns no meaningful evidence → `INSUFFICIENT_EVIDENCE`.
- deletion partial failure → transaction/recovery path; do not report success.
- SQLite WAL/journal cleanup failure → deletion failure; do not report success.
- deletion verification finds any tracked identifier/reference → failure state with counts, not success.
- malformed source file → ingestion report identifies file and continues/halts according to severity.

No silent exception swallowing.

---

# 23. TESTING STRATEGY

Testing is part of implementation, not an end-of-hackathon afterthought.

## Unit tests

At minimum:

- transcript parser,
- email parser,
- report parser,
- report bullet/sub-paragraph granularity,
- Evidence ID stability,
- alias detection,
- corpus-wide alias candidate discovery,
- FTS retrieval,
- vector similarity,
- rank fusion,
- neighbor expansion,
- context-window rendering data,
- validator rejecting nonexistent IDs,
- validator hydrating DB metadata,
- risk rules,
- pseudonymisation target/alias generation and collision handling,
- isolated vault access control and ciphertext-only storage,
- profile history and contribution-quote hydration,
- pseudonymisation dependency lookup and verifier,
- rebuild-after-pseudonymisation does not resurrect original identifiers,
- SQLite WAL/journal cleanup behavior when the configured journal mode uses auxiliary files.

## Integration tests

At minimum:

- ingest → query,
- high-risk query → Skeptic path,
- Skeptic can find an indirect replacement/reversal expressed with different vocabulary,
- query → receipt → UI schema,
- context-dependent citation renders neighbor context,
- pseudonymise person → query again,
- pseudonymisation invalidates dependent Cases/findings for recalculation,
- alias-bearing evidence remains retrievable through the subject profile,
- pseudonymise person → full rebuild → original identity remains absent and the profile graph remains present,
- pseudonymisation verification covers DB auxiliary/cache/vault artifacts owned by the app.

## Privacy/pseudonymisation tests (required for Architecture v1.6)

The old Phase 5 tests are not the acceptance contract. The replacement must prove:

- every subject gets a random UUID `subject_id` and independently cryptorandom, unique, stable `display_alias`;
- aliases are distinct across at least five structurally different targets and never use names, hashes, initials, employee IDs, titles, or sequences;
- the public row transitions to `PSEUDONYMISED` with `pseudonymised_at`, operation ID, and verification result, while the main audit record contains no original name;
- canonical source redaction covers speaker fields, email/report headers, sender addresses, recipients, attendees, signatures, context, inline text, handles, and identifiers, replacing them with the target-specific alias;
- two anonymised people remain distinguishable in source text, retrieval, relationships, and profiles;
- all `evidence_people` relationships, Evidence IDs, locators, Evidence Units, exact contribution quotes, and full profile history survive;
- FTS, embeddings, Cases, receipts, timelines, Radar/Pulse findings, caches, and logs contain no original identifiers or stale pre-pseudonymisation representations;
- the vault stores only authenticated ciphertext and is unreachable from standard repositories, search, embedding, profile, evidence, Case, and log paths;
- a normal UI/API request cannot recover an original name from `subject_id` or `display_alias`;
- only the separately authenticated admin reversal workflow can decrypt and reverse the operation, and its audit record still omits the original name;
- interrupted operations recover safely, remain locked on failure, and never guess from a partial plan;
- a full rebuild from the sanitized canonical source cannot resurrect the original identity or lose the subject's history;
- every destructive/pseudonymising test uses only a temporary source copy and database (section 0.5), never the repository's real `data/source/`, `data/app.db`, or vault.

## Evaluation tests

Build tests around provided practice questions, but do not hardcode answers into reasoning.

Measure:

- relevant evidence retrieval recall,
- expected stance behavior,
- contradiction exposure,
- current-state behavior,
- citation validity,
- deletion correctness.

For non-deterministic LLM semantics, prefer assertions about invariants rather than exact wording.

Example invariants:

```python
assert all(citations_are_valid(receipt))
assert no_deleted_evidence(receipt)
assert high_risk_query_used_skeptic(trace)
assert timeline_events_all_have_evidence(receipt)
```

---

# 24. BUILD PHASES / EXIT CRITERIA

Do not jump directly to frontend polish.

## Phase 0 — Repository + environment

Tasks:

- inspect existing repo,
- create missing structure,
- env configuration,
- DB bootstrapping,
- basic FastAPI health route,
- basic frontend shell.

Exit:

- backend boots,
- frontend boots,
- tests run,
- lint/typecheck run.

## Phase 1 — Evidence Locker (target ~6h)

Tasks:

- implement SQLite schema and repository layer,
- parse all source types,
- handle both named Teams-style transcripts and anonymous `Me:` / `Them:` INTERNAL transcripts,
- preserve/flag truncated statements without completing them,
- normalize known transcript UI chrome without changing meaning,
- create fine-grained Evidence Units,
- create stable source locators and stable Evidence IDs that do not shift after deletion,
- seed people from deterministic roster/header data,
- run corpus-wide alias candidate discovery with explicit stored mappings,
- populate `evidence_people`,
- populate FTS5,
- generate/store embeddings using batching/retry support,
- support `--skip-embeddings` for offline/local ingestion validation,
- create an ingestion report with counts and parsing warnings.

Exit:

- all 45 evidence documents ingest from `data/source/`,
- every Evidence Unit is inspectable by stable Evidence ID,
- anonymous transcript turns remain anonymous,
- truncated units are marked and preserved verbatim,
- deleting/rebuilding an earlier unit does not renumber unaffected surviving Evidence IDs,
- record-count ingestion report exists,
- metadata spot checks pass,
- parser/unit tests pass,
- no Phase 2 retrieval code is required yet.


## Phase 1 review gate

After Phase 1 completes, STOP substantive feature expansion and report the ingestion result before implementing Phase 2.

The report must include:

- files changed,
- total documents parsed by type,
- Evidence Unit counts by document type,
- parse warnings/failures,
- examples of stable source locators/IDs,
- anonymous transcript handling,
- truncation handling,
- people/alias counts,
- unresolved/ambiguous alias candidates,
- FTS row count,
- embedding row count,
- test results,
- any corpus structures that do not fit the current model.

Phase 2 should begin only after Phase 1 output is coherent and the Evidence Locker foundation is trustworthy.

## Phase 2 — Retrieval (target ~5h)

Tasks:

- FTS BM25,
- semantic cosine,
- rank fusion,
- neighbor context,
- temporal sweep.

Exit:

- manual/automated benchmark across at least 10 known topics shows relevant evidence near top results.

## Phase 3 — Primary + Receipt + Validator (target ~6h)

Tasks:

- structured GPT call through the organizer-provided API,
- candidate claim schema,
- receipt schema,
- DB-hydrated citations,
- deterministic validation.

Exit:

- model cannot fabricate displayed date/speaker/doc metadata,
- nonexistent IDs are rejected,
- low-risk question returns valid Case.

## Phase 4 — Risk + Skeptic (target ~5h)

Tasks:

- deterministic risk rules,
- adversarial search generation,
- counter-retrieval,
- reconciliation.

Exit:

- decision/agreement/current-state questions force deep checking,
- Skeptic introduces actual newly retrieved counterevidence when available.

## Phase 5 — Robust pseudonymisation and universal profiles (target ~8h)

Tasks:

- random subject IDs and stable cryptorandom display aliases,
- public `ACTIVE`/`PSEUDONYMISED` profile state and preserved subject graph,
- alias-bearing canonical-source rewriting for all structural and inline identifiers,
- isolated encrypted reversal vault with no standard-query access,
- universal clickable profiles with complete history and contribution quotes,
- source/DB/FTS/embedding/cache/artifact invalidation and rebuild,
- recovery-safe staged operation state and reader/writer privacy gate,
- verification with no original identity in public surfaces or audit records,
- separately authenticated admin reversal and post-operation recalculation.

Exit:

- alias-bearing organizational evidence remains retrievable,
- every participant has a clickable profile with complete history and contribution quotes,
- subject relationships and stable Evidence IDs survive pseudonymisation,
- the public store contains no original target identifiers,
- the vault is ciphertext-only to standard application paths,
- a full rebuild cannot restore the original identity or lose the target graph,
- only the admin reversal workflow can restore an identity,
- operation recovery and verification succeed.

None of this is implemented yet (section 0.1).

## Phase 6 — UI + Decision Evolution (target ~6h)

Tasks:

- Ask page,
- Case view,
- Evidence drawer,
- Decision Evolution timeline,
- Privacy console.

Exit:

- complete live judge flow works without developer intervention.

## Phase 7 — Hardening + Reconsideration Radar innovation (reserve ~7h)

Tasks:

- run practice evaluation repeatedly,
- test malformed model outputs,
- test network/API failures,
- test insufficient evidence,
- test retrieval misses,
- rehearse deletion,
- optimize demo clarity,
- implement the small, precomputed Reconsideration Radar demonstration after
  all core exit criteria pass,
- add the Radar view and Finding Card to the final judge flow,
- run red-team checks for false rejection reasons, changed-condition claims,
  external/internal evidence mixing, and insufficient evidence.

Only after all core exit criteria pass may Project Pulse and Reconsideration
Radar be added. Reconsideration Radar is complete only when every candidate has
an explicit rejected/deferred proposal, an evidence-backed original blocker, a
receipt for the possible changed condition, visible missing information, a
Skeptic result, and a link to a validated Case. It must not produce an
automatic recommendation or free-floating AI finding.

---

# 25. EXPLICITLY OUT OF SCOPE

Do not build during MVP:

- graph database,
- event-calculus truth engine,
- generic ontology framework,
- multi-agent orchestration framework,
- Slack/Teams bot,
- enterprise RBAC,
- multi-tenancy,
- cryptographic provenance,
- cryptographic erasure claims,
- distributed workers,
- Kafka/Redis queues,
- complex auth,
- full document editor,
- exportable PDF unless all core functionality is complete,
- generalized enterprise deployment.

---

# 26. CODE QUALITY / EDITING RULES

## Keep changes surgical

Before editing:

1. inspect relevant files,
2. identify existing conventions,
3. modify the minimum set of files needed.

Do not rewrite working modules without reason.

## No secret leakage

Never:

- commit `.env`,
- print API keys,
- write secrets into tests,
- place secrets in frontend code.

Provide `.env.example`.

## No personal-data debug persistence

Do not write raw prompt/evidence dumps into persistent logs.

Use safe structured traces:

```text
request_id
case_id
model status
retrieval counts
risk flags
evidence IDs
latency
```

During development, if raw debugging is temporarily required, keep it local/ephemeral and remove it before finalization.

## Comments

Comments should explain **why** a guardrail exists, especially around:

- evidence primacy,
- citation hydration,
- deletion,
- risk routing.

Do not comment obvious syntax.

---

# 27. GIT WORKFLOW

Use small milestone commits.

Suggested format:

```text
feat(ingestion): add evidence-unit transcript parser
feat(retrieval): add FTS and semantic rank fusion
feat(reasoning): add structured primary receipt generation
feat(reasoning): add adversarial counter-retrieval
feat(privacy): add physical person purge and verification
feat(ui): add case view and decision timeline
test(evaluation): add practice-question invariants
fix(validation): reject out-of-context evidence IDs
```

Do not commit:

- `.env`,
- runtime database,
- raw model debug dumps,
- generated cache,
- mutable deletion artifacts.

---

# 28. IMPLEMENTATION TRACEABILITY

For each Case request maintain an in-memory or safe minimal trace:

```text
request_id
retrieved evidence IDs
expanded context IDs
risk triggers
whether Skeptic ran
counter-retrieval evidence IDs
final receipt evidence IDs
validation outcome
```

This trace is useful for debugging and demo transparency.

Avoid storing raw personal content in long-lived trace logs.

---

# 29. DEFINITION OF DONE

KEEPER MVP is done when all of the following are true:

1. All challenge documents ingest into stable Evidence Units.
2. Arbitrary questions retrieve relevant evidence without sending the full archive.
3. Primary Reasoner emits structured evidence-ID-backed claims.
4. High-risk decision/current-state questions trigger real counter-retrieval.
5. Final Receipt exposes support, conflict, uncertainty, and resolution.
6. Every displayed citation is hydrated from the DB.
7. Fabricated evidence IDs cannot render.
8. Decision Evolution displays only evidence-backed events.
9. A participant can be pseudonymised with a random `subject_id`, stable cryptorandom `display_alias`, `PSEUDONYMISED` state, operation/timestamp/verification audit fields, and no original identity in public application surfaces.
10. Dependent Cases/artifacts are invalidated.
11. Post-operation verification proves that original identifiers are absent from public source/database/search/derived/log surfaces, the vault contains only encrypted mapping data, and the participant's relationships/history remain intact.
12. Affected Case is recomputed from surviving alias-bearing evidence, and every participant profile can open its complete history.
13. Judges can ask unseen questions through the UI.
14. The live demo works without editing code.
15. The core is tested before optional Project Pulse work begins.

The optional innovation extension is complete only when the Reconsideration
Radar criteria in `docs/RECONSIDERATION_RADAR.md` pass and at least one finding
is surfaced proactively before a judge asks about it.

---

# 30. FINAL IMPLEMENTATION PRINCIPLES

When choosing between two approaches, prefer the one that:

- has fewer moving parts,
- is easier to inspect,
- makes provenance explicit,
- can fail safely,
- can be tested deterministically,
- can be fully pseudonymised/rebuilt,
- can be explained to judges in one sentence.

Never turn a tentative AI interpretation into permanent truth.

Never let an LLM fabricate provenance metadata.

Never hide contradictions.

Never let “newer” automatically mean “true.”

Never hardcode named decision authorities.

Never report pseudonymisation success until public-surface verification, vault verification, relationship preservation, and known dependent-artifact checks pass.

Never let coarse Evidence Units create avoidable deletion collateral damage.

Never show a context-dependent conversational citation without nearby context.

Never treat identity discovery as complete until corpus-wide candidate discovery and post-pseudonymisation verification both pass.

Never let the Skeptic rely only on literal negation; it must search for replacements, later state, and implementation evidence.

Never add architectural complexity merely to make the system look less like RAG.

The differentiator is not the number of agents or databases.

The differentiator is:

> **Evidence → adversarial interpretation when needed → verified receipt → visible decision evolution → preserved history with controlled identity.**
