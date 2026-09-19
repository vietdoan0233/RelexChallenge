# CLAUDE.md — KEEPER: Evidence-First Organizational Memory Auditor

> **Status:** Architecture v1.4 FROZEN — Phase 1 implementation checkpoint recorded; identity hardening, organizer GPT integration, real embeddings, and review are required before Phase 2
> **Challenge:** RELEX Solutions — “Memory With a Receipt”
> **Project:** KEEPER
> **Build model:** 1 developer, ~40 total working hours, AI-assisted implementation
> **Primary objective:** Build the smallest reliable system that can reconstruct organizational truth from a small archive, prove every conclusion with evidence, expose conflicts and supersession, and physically erase a person’s data plus dependent memory.

---

# 0. READ THIS FIRST

This file is the implementation contract.

Do **not** redesign the architecture unless a concrete blocker makes the specified implementation impossible. Do not add frameworks because they seem architecturally elegant. Do not optimize for hypothetical enterprise scale.

The priority order is:

1. Reliability in a live judge demo.
2. Correct evidence provenance.
3. Correct attribution and current-state reasoning.
4. Real deletion and post-deletion recalculation.
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

This section reflects the verified repository state at the end of work on 2026-09-19.

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
  - ingestion CLI/report,
  - unit and integration tests.
- The latest verified offline ingestion parsed 45 documents into 2,517 Evidence Units:
  - 2,115 transcript units,
  - 110 email-message units,
  - 292 report units.
- The latest verified FTS row count is 2,517.
- The latest verified quality gate is 42 passing backend tests, clean Ruff checks, and a successful frontend build.

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

**Phase 1 is implemented but remains at the mandatory review/hardening gate. Phase 2 has not started.**

The following must be resolved before Phase 1 is accepted:

- tighten people/alias discovery so capitalized phrases cannot become deletion-relevant identities,
- review the resulting people/alias/evidence-person counts against the corpus,
- configure a local `.env` without committing secrets,
- finalize the organizer-provided GPT API transport after its endpoint/SDK contract is supplied,
- run one real GPT embedding smoke test,
- generate and verify real embedding rows for the intended corpus before claiming semantic retrieval readiness,
- rerun all Phase 1 quality gates and issue a corrected Phase 1 review report.

The current offline ingestion produced 74 people and 234 aliases, including obvious non-person phrase candidates. This violates the high-confidence identity requirement and is a Phase 1 correctness issue, not a cosmetic cleanup. The runtime database contains zero real embedding rows because no local API configuration was available.

Do not jump to Phase 2 until Phase 1 exit criteria pass and the ingestion output has been reviewed.

---

# 0.2 GITHUB WORKFLOW

The local repository uses the configured `origin` remote. Connector availability varies by session and must be verified rather than assumed.

Use read-only remote inspection where it reduces manual friction, but first verify what actions are actually available in the current environment. The user performs repository `pull`, `fetch`, and `push` operations; give the user the exact command when one is required.

## Required first checks

Before making repository-history changes:

1. inspect the local git status,
2. inspect configured remotes,
3. use local tracking information or an available read-only GitHub connection to verify the intended repository/branch,
4. compare local staged/uncommitted work with the remote before pushing,
5. do not overwrite unrelated remote changes.

## Commit/push behavior

Prefer milestone commits after tests pass.

Create tested local commits when appropriate. Do not run `git pull`, `git fetch`, or `git push`; tell the user which exact command to run and wait for them to perform the network operation.

If local `git commit` is used and identity is missing:

- do not invent an email/name,
- do not change global git identity,
- use a verified connector/account identity only if it is explicitly exposed and appropriate,
- otherwise leave the changes staged/uncommitted and report the commit blocker,
- **missing git identity must never block Phase 1 implementation, testing, or local progress.**

Never force-push unless the user explicitly requests it.

Never rewrite existing remote history for convenience.

## Current history and next milestone

Verified local history at the 2026-09-19 checkpoint:

1. `5886ab5 chore(scaffold): establish keeper phase 0 baseline`
2. `1c6f3d7 feat(ingestion): build evidence locker and stable source parsing`
3. `1bb96b1 fix(ingestion): strip bullet numbering in single-bullet report sections`
4. `c56c252 docs: record phase 1 checkpoint and handoff`

The next milestone is focused Phase 1 hardening for high-confidence identity extraction and, once the organizers supply the API contract, the GPT adapter and real embedding verification. Do not label Phase 2 complete or semantic retrieval ready until real embedding rows exist.

Use an available GitHub connection only for read-only work such as:

- verifying remote repository state,
- inspecting branch/history,
- reviewing diffs.

Do not let GitHub integration change the architecture or source-of-truth rules.

# 0.3 CONTRACT VERSION HISTORY

The architecture version changes only when the frozen product or technical architecture changes. Updating implementation progress, repository state, test counts, or handoff notes does **not** create a new architecture version.

- **v1.4 — current, frozen.** Replaced the Google/Gemini provider choice with an organizer-provided GPT service. The API key, base URL, reasoning model, and embedding model remain environment placeholders until the organizers supply the exact contract. The provider-neutral offline ingestion path remains mandatory.
- **v1.3 — previous frozen architecture.** Audited architecture contract covering the Phase 0 checkpoint, GitHub workflow, stable source-locator manifest, canonical-source rebuild invariant, embedding resilience, citation-context invariant, Skeptic counter-retrieval behavior, deletion cleanup, and mandatory Phase 1 review gate.
- **2026-09-19 implementation checkpoint — no architecture version change.** Recorded the implemented Phase 1 Evidence Locker, verified offline ingestion/test counts, known identity-discovery false positives, missing real embeddings, and the decision to stop before Phase 2.

Earlier architecture iterations are not reconstructed here because their authoritative change notes are not present in the repository. Do not invent retrospective version details.

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

## 2.4 Deletion

Judge requirement: every application-owned trace of the deleted person must disappear.

Do not implement deletion as:

- prompt filtering,
- blacklist,
- query-time hiding,
- `is_deleted = TRUE`,
- name masking.

Deletion must cover, where applicable:

- source/raw text under application control,
- normalized text,
- evidence units,
- people/alias mappings,
- FTS records,
- embeddings,
- derived annotations,
- receipts,
- cached Cases,
- timeline events,
- Project Pulse findings,
- caches and persisted generated artifacts,
- debug artifacts containing the person or deleted evidence IDs.

Affected conclusions must be recalculated from surviving evidence.

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
DATABASE_PATH=./data/keeper.db
SOURCE_DATA_DIR=./data/source
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
│   ├── keeper.db                # runtime DB, gitignored
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
│   │   │   ├── purge.py
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

**Deletion-radius rule:** For KEEPER's chosen whole-unit deletion strategy, Evidence Units should be as small as practical without destroying meaning. This is especially important for reports. Do not store an entire multi-bullet engineering/status section as one Evidence Unit if the bullets can stand independently.

Long units may be split, but they must retain the same source relationship, parent document, sequence, and neighbor relationships.

Do not default to blind fixed-token chunking.

The reason for this granularity is privacy as well as retrieval quality: deleting one person should not unnecessarily erase unrelated facts that happened to share a large coarse chunk.

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
    person_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE
);

CREATE TABLE person_aliases (
    alias_id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    UNIQUE(person_id, alias)
);

CREATE TABLE evidence_people (
    evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
    relation TEXT NOT NULL, -- AUTHOR | SPEAKER | MENTIONED
    PRIMARY KEY (evidence_id, person_id, relation)
);

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

---


## Canonical source boundary for this hackathon

`data/source/` is KEEPER's **application-owned canonical working source** for ingestion, rebuild, and deletion behavior.

The untouched challenge extraction outside `data/source/` is a **development fixture/reference input**, not application memory.

Rules:

- runtime ingestion and rebuild commands must read from `data/source/`,
- deletion must sanitize the relevant content in `data/source/`,
- a normal KEEPER rebuild must never silently re-import from the untouched fixture,
- the untouched fixture must remain gitignored and outside application persistence,
- tests may use isolated fixture copies, but production/runtime code must not use the untouched archive as a fallback source.

This distinction is required so:

```text
purge person
→ verify
→ rebuild
→ verify again
```

cannot resurrect deleted evidence.

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

# 18. TRUE DELETION

Deletion is a core scoring requirement.

## 18.1 Deletion target expansion

When deleting person P:

resolve:

- canonical name,
- known email(s),
- stored safe aliases.

Find every Evidence Unit where P is:

- AUTHOR,
- SPEAKER,
- MENTIONED.

For this challenge, prefer deleting the entire **small, well-formed Evidence Unit** containing the target person rather than attempting fragile sentence-level redaction.

For KEEPER's chosen whole-unit purge strategy, fine ingestion granularity is necessary to minimize collateral deletion:

- transcript unit → normally one speaker turn,
- email unit → one message,
- report unit → one bullet / short factual sub-paragraph where possible.

This means a statement such as:

> “Kwame told me the extraction succeeded.”

is deleted even if someone else said it.

That is intentional: the target person remains part of the informational trace.

However, the parser must avoid coarse units that bundle unrelated facts, because whole-unit deletion should not create unnecessary organizational amnesia.

## 18.1.1 Canonical source and rebuild safety

A purge is incomplete if a later rebuild can silently resurrect deleted data.

Therefore:

- the app-owned canonical source used for rebuilds must itself be sanitized during deletion,
- any app-owned normalized manifests/copies must be sanitized too,
- rebuild scripts must read only from the sanitized canonical source or sanitized manifest,
- no hidden unsanitized backup may remain inside application-owned runtime/storage directories.

If the original hackathon corpus is treated as external/read-only input outside KEEPER's owned persistent state, keep that boundary explicit in code and documentation. Do not copy an untouched version into app-owned storage and later rebuild from it after deletion.

A successful purge must preserve this invariant:

> running the normal rebuild command after deletion must not resurrect the deleted person's data.

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

## 18.4 Physical purge sequence

Implement a transactional/safe sequence:

```text
resolve person + aliases
    ↓
identify target evidence IDs
    ↓
identify dependent Cases/findings
    ↓
physically scrub/remove corresponding source content under app control
    ↓
DELETE evidence rows
    ↓
DELETE embedding rows
    ↓
DELETE/refresh FTS rows
    ↓
DELETE dependent Cases
    ↓
DELETE dependent Pulse findings
    ↓
clear relevant runtime caches/artifacts
    ↓
checkpoint/truncate SQLite WAL or journal state as applicable
    ↓
VACUUM SQLite
    ↓
close/reopen database and verify auxiliary DB files
    ↓
rebuild retrieval representations as needed
    ↓
recompute active affected Case from surviving evidence
    ↓
run deletion verifier
```

Do not keep a hidden personal-data backup inside `data/`.

If an external original file outside application control exists, document that it is external input, not retained internal state. All application-owned copies must be purged.

## 18.3.1 SQLite physical-cleanup details

Row deletion alone is not enough to claim application-level physical purge.

SQLite may retain recently deleted bytes in:

- the main database file,
- `-wal`,
- `-shm`,
- rollback journal/temp files,
- application caches.

Implementation must account for the configured journal mode.

At purge time:

1. complete transactional deletes,
2. checkpoint/truncate WAL if WAL mode is enabled,
3. remove/clear stale auxiliary DB artifacts when safe and appropriate,
4. run `VACUUM`,
5. close and reopen the database,
6. verify the main DB and relevant auxiliary/cache artifacts for tracked identifiers and deleted evidence IDs.

Do not report deletion success while a stale WAL/journal/cache still contains tracked deleted data.

---

## 18.4 Logging

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

Deletion is not “successful” until a verifier checks:

- source files under app control,
- database text fields,
- aliases,
- FTS,
- cached JSON,
- Case JSON,
- Pulse JSON,
- runtime artifacts,

for:

- target canonical name,
- aliases/emails,
- deleted evidence IDs.

Expected result for all **tracked identifiers and references**:

```text
0 surviving matches for canonical name / known aliases / known emails
0 deleted evidence references
0 surviving embedding rows for deleted evidence
0 stale references in Cases / timelines / Pulse / caches
```

This is a strong application-level verification over what the system knows and owns. Do not describe it as a mathematical proof that no unknown alias or indirect reference could exist.

Then rerun an affected Case and show the new result.

Use accurate wording:

> application-level physical purge with dependency invalidation and post-deletion verification

Do **not** claim cryptographic erasure.

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

## D. Privacy Console

Select a person, preview affected counts, execute deletion, display progress, verify purge, and show post-deletion recalculation.

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
POST /api/privacy/purge

GET  /api/health
```

Optional:

```text
GET /api/pulse
```

`POST /api/cases/query` returns a validated Case object, not arbitrary Markdown.

`GET /api/evidence/{evidence_id}` returns exact DB-hydrated source metadata/text.

Deletion endpoint returns counts and verification state, not deleted personal content.

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
- deletion dependency lookup,
- deletion verifier,
- rebuild-after-delete does not resurrect deleted data,
- SQLite WAL/journal cleanup behavior when the configured journal mode uses auxiliary files.

## Integration tests

At minimum:

- ingest → query,
- high-risk query → Skeptic path,
- Skeptic can find an indirect replacement/reversal expressed with different vocabulary,
- query → receipt → UI schema,
- context-dependent citation renders neighbor context,
- delete person → query again,
- evidence deletion invalidates Cases,
- deleted evidence cannot be retrieved,
- delete person → full rebuild → deleted evidence remains absent,
- deletion verification covers DB auxiliary/cache artifacts owned by the app.

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

## Phase 5 — Deletion (target ~5h)

Tasks:

- preview dependencies,
- purge,
- source scrub,
- DB/index/cache purge,
- `VACUUM`,
- verification,
- affected Case recalculation.

Exit:

- all tracked identifiers, aliases, emails, deleted evidence IDs, and known dependent references have zero surviving matches in application-owned persistence,
- deleted evidence cannot be retrieved,
- a full rebuild does not resurrect deleted evidence,
- SQLite auxiliary persistence (WAL/journal/temp state as applicable) is cleaned/verified,
- affected Case changes appropriately.

## Phase 6 — UI + Decision Evolution (target ~6h)

Tasks:

- Ask page,
- Case view,
- Evidence drawer,
- Decision Evolution timeline,
- Privacy console.

Exit:

- complete live judge flow works without developer intervention.

## Phase 7 — Hardening (reserve ~7h)

Tasks:

- run practice evaluation repeatedly,
- test malformed model outputs,
- test network/API failures,
- test insufficient evidence,
- test retrieval misses,
- rehearse deletion,
- optimize demo clarity.

Only after all core exit criteria pass may Project Pulse be added.

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
9. A person can be physically purged from application-owned raw/normalized/search/derived storage.
10. Dependent Cases/artifacts are invalidated.
11. Post-deletion verification returns zero surviving matches for all tracked identifiers, deleted evidence IDs, and known dependent artifacts.
12. Affected Case is recomputed from surviving evidence.
14. Judges can ask unseen questions through the UI.
15. The live demo works without editing code.
16. The core is tested before optional Project Pulse work begins.

---

# 30. FINAL IMPLEMENTATION PRINCIPLES

When choosing between two approaches, prefer the one that:

- has fewer moving parts,
- is easier to inspect,
- makes provenance explicit,
- can fail safely,
- can be tested deterministically,
- can be fully deleted/rebuilt,
- can be explained to judges in one sentence.

Never turn a tentative AI interpretation into permanent truth.

Never let an LLM fabricate provenance metadata.

Never hide contradictions.

Never let “newer” automatically mean “true.”

Never hardcode named decision authorities.

Never report deletion success until verification passes for all tracked identifiers, deleted evidence IDs, and known dependent artifacts.

Never let coarse Evidence Units create avoidable deletion collateral damage.

Never show a context-dependent conversational citation without nearby context.

Never treat alias discovery as complete until corpus-wide candidate discovery and post-delete verification both pass.

Never let the Skeptic rely only on literal negation; it must search for replacements, later state, and implementation evidence.

Never add architectural complexity merely to make the system look less like RAG.

The differentiator is not the number of agents or databases.

The differentiator is:

> **Evidence → adversarial interpretation when needed → verified receipt → visible decision evolution → true memory deletion.**
