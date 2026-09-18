# CLAUDE.md — KEEPER: Evidence-First Organizational Memory Auditor

> **Status:** Architecture v1.0 FROZEN  
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
- Google GenAI SDK directly
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
GOOGLE_API_KEY=
GEMINI_MODEL=
GEMINI_EMBEDDING_MODEL=
DATABASE_PATH=./data/keeper.db
SOURCE_DATA_DIR=./data/source
```

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
- report → one paragraph or coherent section.

Long units may be split, but they must retain the same source relationship and sequence.

Do not default to blind fixed-token chunking.

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

Evidence IDs must be deterministic or stable across normal re-ingestion whenever the corresponding source unit survives.

Example:

```text
EV-<document slug>-<unit index>
```

Do not let routine rebuilds randomly change all evidence IDs unless unavoidable.

Deletion/rebuild must not resurrect deleted evidence.

---

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

## People detection

Prefer deterministic identity extraction from:

- transcript speaker labels,
- email sender/from headers,
- email addresses,
- clearly named participants,
- unique full-name mentions.

Aliases may include:

- full name,
- email,
- safe unique name variants.

Avoid broad fuzzy aliases that risk deleting unrelated text.

---

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

Purpose: the LLM must not interpret isolated lines like “yes” without the preceding proposal.

Do not over-expand until the context is the whole archive.

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
2. generate 1–3 adversarial retrieval intentions,
3. run them through the same retrieval service,
4. inspect returned counterevidence,
5. output objections and counterevidence IDs.

Examples of adversarial intentions:

- later reversal,
- explicit disagreement,
- lack of confirmation,
- proposal-only language,
- operational behavior contradicting a status report,
- later implementation inconsistent with stated agreement,
- evidence that the supposed commitment applied only to a narrower scope.

The Skeptic must perform actual counter-retrieval. A prompt-only critique without new retrieval is insufficient.

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

For this challenge, prefer deleting the entire evidence unit containing the target person rather than attempting fragile sentence-level redaction.

This means a statement such as:

> “Kwame told me the extraction succeeded.”

is deleted even if someone else said it.

That is intentional: the target person remains part of the informational trace.

## 18.2 Dependency invalidation

Before deleting evidence, identify dependent:

- Cases,
- timeline events,
- Pulse findings.

Use the relational reference tables, not a graph database.

## 18.3 Physical purge sequence

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
VACUUM SQLite
    ↓
rebuild retrieval representations as needed
    ↓
recompute active affected Case from surviving evidence
    ↓
run deletion verifier
```

Do not keep a hidden personal-data backup inside `data/`.

If an external original file outside application control exists, document that it is external input, not retained internal state. All application-owned copies must be purged.

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

Expected result:

```text
0 surviving textual traces
0 deleted evidence references
0 surviving embedding rows for deleted evidence
```

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
- Gemini unavailable → API returns explicit temporary analysis failure, not fabricated answer.
- fabricated evidence ID → drop/reject claim.
- retrieval returns no meaningful evidence → `INSUFFICIENT_EVIDENCE`.
- deletion partial failure → transaction/recovery path; do not report success.
- deletion verification nonzero → failure state with counts, not success.
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
- Evidence ID stability,
- alias detection,
- FTS retrieval,
- vector similarity,
- rank fusion,
- neighbor expansion,
- validator rejecting nonexistent IDs,
- validator hydrating DB metadata,
- risk rules,
- deletion dependency lookup,
- deletion verifier.

## Integration tests

At minimum:

- ingest → query,
- high-risk query → Skeptic path,
- query → receipt → UI schema,
- delete person → query again,
- evidence deletion invalidates Cases,
- deleted evidence cannot be retrieved.

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

- parse all source types,
- Evidence Units,
- stable IDs,
- people/aliases,
- SQLite,
- FTS,
- embeddings.

Exit:

- every source passage is inspectable by stable Evidence ID,
- record-count ingestion report exists,
- metadata spot checks pass.

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

- structured Gemini call,
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

- target aliases/data/evidence IDs have zero surviving application-owned traces,
- deleted evidence cannot be retrieved,
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
11. Post-deletion verification returns zero traces.
12. Affected Case is recomputed from surviving evidence.
13. Judges can ask unseen questions through the UI.
14. The live demo works without editing code.
15. The core is tested before optional Project Pulse work begins.

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

Never report deletion success until verification passes.

Never add architectural complexity merely to make the system look less like RAG.

The differentiator is not the number of agents or databases.

The differentiator is:

> **Evidence → adversarial interpretation when needed → verified receipt → visible decision evolution → true memory deletion.**
