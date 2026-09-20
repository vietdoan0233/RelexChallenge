# Organizational Memory Auditor

This project is our solution to the RELEX Solutions **“Memory With a Receipt”** challenge at the AaltoAI Hackathon 2026.

The temporary internal codename is **KEEPER**. It is only a project name; the final product name has not been chosen. The application can use a different display name through `APP_NAME` and `VITE_APP_NAME`.

**Status:** The core demo is implemented end to end. The 45-document archive produces
2,534 stable Evidence Units, an SQLite FTS5 index, and a runtime database prepared for
1,536-dimensional embeddings. The application now includes hybrid retrieval, structured
Cases with validated receipts, risk-based Skeptic checking, Decision Evolution, participant
profiles, Architecture v1.6 pseudonymisation with an isolated encrypted reversal vault,
plain-text evidence upload, and the precomputed Reconsideration Radar.

The dated phase reviews document historical quality gates and live checks. [`AGENTS.md`](AGENTS.md)
is the authoritative current implementation contract, especially for the v1.6 privacy
workflow. The current build is demo-ready when the organizer GPT credentials are present;
without them the archive, ingestion, lexical retrieval, UI, and tests still work, but live
Case generation and Radar precomputation are unavailable.

## Five-minute localhost demo

Prerequisites: Python 3.11+, Node.js/npm, and the repository's prepared `data/app.db`.
For the full experience, configure the organizer's OpenAI-compatible GPT service in the
root `.env`. The reasoning fields are required for Ask and Radar; the embedding fields enable
semantic retrieval and complete readiness checks.

From the repository root:

```powershell
# One-time setup
Copy-Item .env.example .env
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd ..\frontend
npm ci
npm run build

# Start the one-process demo server
cd ..\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000). When `frontend/dist` exists, FastAPI
serves the built React UI and the `/api` endpoints from the same origin.

For macOS/Linux, activate the virtual environment with `source .venv/bin/activate` and use
the same `npm ci`, `npm run build`, and `python -m uvicorn app.main:app --reload --port 8000`
commands from the equivalent directories.

Suggested five-minute walkthrough:

1. On **Ask**, try `Did Acme sign off UAT, and what exactly was the scope?` or
   `How did the bakery scope change over time?`.
2. Open the generated **Case**. Show the verdict, claim-level support, conflicts,
   confidence, uncertainty, the risk/review panel, and the exact evidence drawer.
3. Scroll to **Decision Evolution** to show how a proposal, agreement, implementation
   update, and later change are separated instead of flattened into one answer.
4. Open **Radar** to show precomputed rejected/deferred ideas, their original blockers,
   later evidence, and the bounded `STILL_BLOCKED`/`PARTIALLY_CHANGED`/
   `WORTH_REASSESSING`/`INSUFFICIENT_EVIDENCE` assessment.
5. Open **Privacy** to preview a participant's impact. Only run the destructive
   pseudonymisation step against a disposable copy; instructions are below.

The browser development mode is also available. Keep the backend on port 8000, then run:

```bash
cd frontend
npm run dev -- --port 3000
```

Open [http://localhost:3000](http://localhost:3000); Vite proxies `/api` to the backend.

## The challenge in simple terms

Imagine joining a company and asking:

> “What was decided about the Fresh project, who agreed to it, what happened afterwards, and is it still true?”

The answer may be spread across meeting transcripts, emails, and status reports. Some messages suggest an idea, some object to it, some agree to it, and later messages may change or contradict it. A normal chatbot might find a few matching sentences and confidently combine them into an answer. That is exactly where it can go wrong.

The challenge asks us to build a small organizational memory system that can answer these questions with proof. It must explain:

- what actually happened;
- what was only proposed or assumed;
- what became an agreement or commitment;
- what is currently true;
- whether later evidence changed or contradicted an earlier decision;
- which exact source passages support each important statement;
- which evidence disagrees;
- how certain the answer is; and
- what happens to the memory when a person is pseudonymised.

The archive is intentionally small enough to inspect, but complicated enough to expose these problems:

- 45 evidence documents;
- 20 email threads;
- 2 report threads;
- 23 meeting transcripts;
- approximately 57,000 words;
- dates from March 2024 to July 2026; and
- conversations about the fictional retailer **Acme Org**.

The judges can ask questions that we have not seen beforehand. They can also request a participant pseudonymisation while watching whether the system removes the original identity from ordinary application surfaces, preserves attributable history, and recalculates affected conclusions.

## What we are building

Our product is an **AI organizational memory auditor**. A useful way to think about it is:

> a research assistant that finds the relevant conversations, a fact-checker that looks for disagreement, and a receipt printer that shows exactly where every conclusion came from.

The central idea is the **Evidence Locker**. The original source material stored by the application is the authority. The AI is only an interpreter: it helps organize and explain the evidence, but it is not allowed to invent facts or replace the source material.

Every user question is treated as a **Case**. A Case is not just a chat reply. It should contain:

- a clear conclusion;
- separate claims that make up the conclusion;
- supporting evidence for each claim;
- conflicting or weakening evidence;
- who said or wrote each relevant thing;
- whether the statement was a suggestion, objection, agreement, commitment, update, or implementation proof;
- remaining uncertainty;
- an explanation of why one interpretation is stronger; and
- a timeline showing how the decision changed when that is useful.

Our standout feature is **Decision Evolution**: instead of showing only the latest matching sentence, the system should tell the story of a decision from proposal to discussion, agreement, implementation, change, or unresolved conflict.

## How the finished system should work

When somebody asks a question, the intended flow is:

1. **Find the evidence.** Search the archive using both exact words and meaning. For a question about a decision, also look for later updates that may have changed it.
2. **Build a first answer.** The Primary Reasoner reads the selected evidence and creates structured claims rather than a free-form guess.
3. **Judge the risk.** A simple risk step checks whether the answer involves a major decision, a person, conflicting information, or weak evidence.
4. **Look for the opposite case when needed.** For medium- and high-risk answers, the Skeptic searches specifically for evidence that could disprove, weaken, or supersede the first answer.
5. **Reconcile the evidence.** The Primary Reasoner considers the challenge from the Skeptic and explains why the final interpretation is the best-supported one.
6. **Validate the receipt.** A deterministic checker confirms that every citation points to a real stored Evidence Unit and that the quoted text actually matches the database.
7. **Show the Case.** The user sees the conclusion, uncertainty, supporting evidence, conflicts, decision timeline, and original source receipts.

Newer evidence is not automatically treated as correct. A recent status report can still conflict with operational evidence. The system must show the conflict and explain whether an older statement was superseded, remains useful, or is simply unverified.

## What we have implemented so far

### 1. The source archive is under our control

We copied the 45 challenge documents into `data/source/`, which is the application’s canonical working copy. The application reads evidence only from the email, report, and transcript folders inside that directory. Reference files such as practice questions are kept outside those folders so they cannot accidentally become evidence.

This boundary matters because the application must know exactly which material it is allowed to remember, search, cite, and later sanitize.

### 2. The archive is converted into small pieces of evidence

We do not treat an entire transcript or report as one giant block. We split the archive into practical Evidence Units:

- one speaker turn in a transcript;
- one message in an email thread; and
- one bullet, short paragraph, or small factual section in a report.

Small units make search and citations clearer. They also reduce collateral damage if one person’s data later needs to be removed: unrelated facts should not disappear just because they were stored beside that person in a huge text block.

The latest verified ingestion produced **2,534 Evidence Units** (2,517 at the Phase 1 gate; the Guest N caption fix added 17 transcript units):

- 2,132 transcript units;
- 110 email-message units; and
- 292 report units.

The parser keeps useful context with each unit, including the source document, date, speaker or sender, thread context, timestamp text, and the original wording.

### 3. We preserve the source instead of “correcting” it

The archive contains intentionally incomplete statements. For example, a sentence or number may end abruptly. The parser records that a unit is truncated instead of guessing how the sentence should have ended.

The archive also contains anonymous `Me:` / `Them:` conversations. We preserve those labels and do not pretend to know who those people really are. A person mentioned inside an anonymous conversation can still be recorded as mentioned, but the anonymous speaker is not silently assigned to that person.

Known transcript formatting noise, repeated interface text, and image placeholders are handled with deterministic rules. The purpose is to remove obvious export clutter without changing the meaning of the original statement.

### 4. Evidence IDs remain stable

Each Evidence Unit receives a stable identifier and a source locator. The locator acts like a permanent address inside the original document. If a participant is pseudonymised later, the surviving evidence keeps its address and the alias-bearing rebuild must not resurrect the original identity.

This is important for receipts: a citation should continue to point to the same source location, not merely to “whatever happens to be item 17 after the next import.”

### 5. People and relationships are handled cautiously

The system records people who appear as:

- an email or report author;
- a transcript speaker; or
- a person mentioned in the text.

The latest verified counts are:

- **25 people**;
- **39 aliases**;
- **402 AUTHOR relationships**;
- **1,964 SPEAKER relationships**; and
- **242 MENTIONED relationships**.

This part required extra care. A capitalized phrase inside a sentence can look like a name even when it is actually a project phrase, job title, or transcription error. Earlier extraction logic produced false identities such as “Risk Fresh Phase,” “This So,” and “Slight Delay Bakery.” Those false identities are now absent.

Real people found only in text are added through a human-reviewed identity file, `data/source/reviewed_identities.json`. Short forms such as first names, last names, initials, nicknames, and spelling variants are also added only when explicitly reviewed. A name being unique in the archive is not enough to *promote* it into the alias table. Pseudonymisation is stricter in a different way: it treats a person's full name and their bare first name as the same participant, rewriting both, whenever that first name belongs to nobody else (`backend/app/ingestion/name_resolution.py`). A first name shared by two people, such as the two Nadias, is never guessed and is reported as left unchanged.

This conservative rule protects the privacy operation. If the system mistakenly turns an ordinary phrase into a person, it could later rewrite or hide unrelated organizational memory.

### 6. Keyword search is ready

The Evidence Locker has an SQLite full-text search index containing **2,534 rows**, one for each Evidence Unit. This gives us a dependable offline way to find evidence using words from the user’s question.

We have also created a provider-neutral embedding interface. Embeddings are numerical summaries that help find passages with similar meaning even when they do not use exactly the same words. Tests use a deterministic local mock, and the runtime database holds real 1,536-dimensional embeddings for all 2,534 units, generated with the organizer-provided GPT embedding service. Without that service configured, ingestion still completes with keyword search only and reports the embeddings as skipped.

### 7. Ingestion can be rerun safely for development

The ingestion process can rebuild the derived evidence tables from the canonical source. It validates the source files and reviewed identity file before clearing rebuildable data. People and aliases are regenerated from the sanitized inputs so stale or false identities do not live forever in the database.

The source-locator manifest is kept separately so normal rebuilding does not renumber old source locations. This is the foundation needed for reliable pseudonymisation and recalculation.

### 8. The judge-facing product flow is implemented

The backend exposes the archive, retrieval, Cases, evidence context, people,
privacy, readiness, ingestion, and Radar APIs. The frontend is a React, Vite,
TypeScript, and Tailwind application with configurable neutral branding and a
single-origin production mode served by FastAPI.

The UI includes:

- **Ask:** archive stats, example questions, recent Cases, and a guided thinking state;
- **Case:** verdict, claim-level stance/confidence, support and conflict receipts,
  review/Skeptic details, uncertainty, related questions, and Decision Evolution;
- **Evidence drawer:** the cited unit plus neighbouring context, document/thread/date/
  speaker metadata, and preserved truncation warnings;
- **People:** a participant's complete attributable evidence history;
- **Privacy:** searchable participants, impact preview, typed confirmation, progress,
  verification, pseudonymisation, and the authenticated admin-only reversal path;
- **Add Evidence:** bounded `.txt` upload for email, transcript, and report sources;
  live Slack/Teams/Drive connectors are intentionally not part of this build; and
- **Radar:** precomputed reconsideration findings with internal evidence, external
  signals, assessment, missing information, and links back to validated Cases.

## Current progress at a glance

| Area | Current state |
| --- | --- |
| Project setup | Complete |
| Backend and frontend boot | Complete |
| Challenge archive copied into application-owned storage | Complete |
| Email, report, and transcript parsing | Complete for the current archive |
| Evidence Units and stable source locators | Complete |
| Truncation and anonymous-speaker handling | Complete |
| People, aliases, and relationship linking | Complete; identity hardening finished |
| SQLite Evidence Locker and full-text search | Complete |
| Offline ingestion and deterministic mock embeddings | Complete |
| Real GPT embedding generation | Supported when organizer credentials are configured; runtime database is prepared with 1,536-dimensional vectors |
| Primary question answering | Complete: structured, receipt-backed Case generation |
| Semantic retrieval and hybrid retrieval | Complete: FTS5 + NumPy cosine + deterministic rank fusion + context/later-evidence sweep |
| Skeptic and risk-based checking | Complete: deterministic risk routing, counter-retrieval, objections, reconciliation |
| Case UI and Decision Evolution | Complete and browser-verified |
| Participant profiles | Complete: full attributable history survives pseudonymisation |
| Pseudonymisation and reversal | Complete in the v1.6 implementation; isolated encrypted vault and authenticated admin reversal |
| Evidence upload | Complete for bounded plain-text email, transcript, and report uploads |
| Reconsideration Radar | Complete as a precomputed, evidence-bounded feature; live discovery may surface only a small number of findings |

The project has backend unit/integration/evaluation coverage plus Ruff, frontend
typecheck, lint, and production-build checks. Run the commands below before a
judge rehearsal. Live model wording is intentionally non-deterministic; the
important guarantees are valid citations, bounded claims, explicit uncertainty,
and safe degradation when a provider is unavailable.

## Current directions and remaining work

The core architecture is intentionally frozen: keep the Evidence Locker as the
source of truth, keep the LLM in the interpreter role, and prefer deterministic
validation over extra agent frameworks. The highest-value next work is demo
hardening rather than adding infrastructure:

1. Rebuild and gate the runtime database from the canonical source before a
   rehearsal; `/api/readiness` and `python scripts/smoke.py` are the release checks.
2. Re-run the live practice questions against the exact organizer model and keep
   the demo questions focused on decisions, current state, conflicts, and UAT.
3. Curate a few real external signals if the Radar needs a stronger live story;
   `data/source/external_signals.json` is empty on purpose and the system never
   scrapes the web or invents outside evidence.
4. Add automated frontend tests and, if time allows, improve retrieval for broad
   enumerative questions and varied model phrasing.
5. Treat the privacy operation as pseudonymisation, not irreversible anonymisation:
   known identifiers are rewritten to a stable participant alias, relationships and
   Evidence IDs survive, derived Cases/findings are invalidated, and the original
   identity is recoverable only through the authenticated admin workflow.

## Running the project locally

### Configuration

Copy `.env.example` to `.env` at the repository root. The real `.env` is ignored by Git
and is the only place for credentials.

For a full live demo, configure `GPT_API_KEY`, `GPT_BASE_URL`, `GPT_MODEL`, and
`GPT_EMBEDDING_MODEL`. Configure `PSEUDONYM_VAULT_KEY` with a fresh Fernet key and set
`PRIVACY_ADMIN_TOKEN` if you want to exercise the authenticated Privacy action. The UI
can load the archive without GPT credentials, but Ask returns a clear unavailable response
until the reasoning service is configured.

Generate a vault key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Frontend development with hot reload

```bash
cd frontend
npm ci
npm run dev -- --port 3000
```

Keep the backend running on port 8000. Vite proxies `/api` to it, so open
<http://localhost:3000>.

### Safe privacy rehearsal

Pseudonymisation rewrites the configured canonical source and invalidates dependent
derived records. It is intentionally persistent for that instance. Before showing it
live, use a disposable copy of the source and database. In Windows PowerShell:

```powershell
$demoRoot = Join-Path (Get-Location) ".demo-data"
New-Item -ItemType Directory -Force $demoRoot | Out-Null
Copy-Item data\source (Join-Path $demoRoot "source") -Recurse
Copy-Item data\app.db (Join-Path $demoRoot "app.db")

$env:DATABASE_PATH = Join-Path $demoRoot "app.db"
$env:SOURCE_DATA_DIR = Join-Path $demoRoot "source"
$env:PSEUDONYM_VAULT_PATH = Join-Path $demoRoot "private-vault\vault.db.enc"
$env:PSEUDONYM_VAULT_KEY = (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
$env:PRIVACY_ADMIN_TOKEN = "demo-admin-token"
```

Start the backend after setting those variables. Enter `demo-admin-token` in the Privacy
console when it asks for the admin credential. If the copied database is missing or stale,
rebuild only the copy with `python scripts/ingest.py --source $env:SOURCE_DATA_DIR --db-path $env:DATABASE_PATH`
and the configured embedding provider; never point a destructive rehearsal at the repository
source unless that persistence is intentional.

### Run the current offline ingestion

From the repository root, the parser and Evidence Locker can be rebuilt without network access:

```bash
python scripts/ingest.py --skip-embeddings --db-path /tmp/scratch.db
```

> Ingestion rebuilds every derived table, **including the embeddings**. Run it against the runtime `data/app.db` only when you intend to regenerate them (that re-sends the archive to the embedding provider); use `--db-path` for scratch work.

The command parses the archive, rebuilds the evidence tables, creates the full-text search index, links people to evidence, and prints an ingestion report. The `--skip-embeddings` option is for offline development without credentials.

The organizer service is verified as OpenAI-compatible at `/v1/embeddings` (bearer authentication, `{model, input}` requests, numeric vectors in the response). With `GPT_API_KEY`, `GPT_BASE_URL`, and `GPT_EMBEDDING_MODEL` configured in the gitignored root `.env`, real vectors can be generated with:

```bash
python scripts/ingest.py
```

Do not claim semantic retrieval is ready until the ingestion report confirms real embedding rows for the intended corpus. The API's `/api/readiness` endpoint performs the same kind of runtime gate and returns HTTP 503 when the archive is stale, incomplete, or missing valid embeddings.

### Run checks

```bash
cd backend
pytest -q
ruff check app tests ../scripts
ruff format --check app tests ../scripts
```

```bash
cd frontend
npm run typecheck
npm run build
```

## A small glossary

| Term | Meaning in this project |
| --- | --- |
| Evidence Locker | The database-backed memory of the application. The stored source evidence is authoritative. |
| Evidence Unit | A small, useful piece of a document, such as one email or one speaker turn. |
| Receipt | The source citation and exact text that lets a person check a claim. |
| Case | The saved, structured result of one user question. |
| Primary Reasoner | The main AI role that turns selected evidence into claims. |
| Skeptic | A second AI role used for riskier answers to search for counter-evidence. |
| Decision Evolution | The history of how a proposal became, changed, or failed to become a decision. |
| Embedding | A numerical representation used to find passages with similar meaning. |
| Rebuild | Recreating derived database tables from the canonical source files. |

## Project documents

- [`AGENTS.md`](AGENTS.md) — the implementation contract and current checkpoint.
- [`CLAUDE.md`](CLAUDE.md) — the full architecture, frozen decisions, and phase plan.
- [`docs/HANDOFF_2026-09-19.md`](docs/HANDOFF_2026-09-19.md) — an earlier handoff snapshot; the current checkpoint is in `AGENTS.md`.
- [`data/ARCHIVE_README.md`](data/ARCHIVE_README.md) — description of the challenge archive.
- [`data/PRACTICE_QUESTIONS.md`](data/PRACTICE_QUESTIONS.md) — practice questions for later retrieval/evaluation work; these are not evidence.

## Reconsideration Radar

The Radar surfaces ideas the organization rejected or deferred where the stated
reason for saying no may have changed. It only ever says `STILL_BLOCKED`,
`PARTIALLY_CHANGED`, `WORTH_REASSESSING` or `INSUFFICIENT_EVIDENCE`, keeps internal
evidence, external signals and its own assessment visibly separate, and shows what
it cannot establish. Findings are precomputed (never per page load), each linked to
a validated Case and to Evidence Units.

```bash
python scripts/radar.py --limit 5
```

This sends retrieved evidence excerpts to the configured organizer reasoning
service and stores the findings in the runtime database. Curated outside
developments go in `data/source/external_signals.json`, which ships empty: the
system never scrapes the web or invents an external signal. The findings appear
under **Radar** in the UI. See [docs/RECONSIDERATION_RADAR.md](docs/RECONSIDERATION_RADAR.md).

## Innovation and product direction

The product's differentiator is not a larger chat window. It is an auditable
memory loop: retrieve the relevant record, model the competing interpretations,
validate every cited receipt against the database, preserve the decision's
evolution, and show what changed later. The Radar extends that loop proactively
by surfacing old rejected or deferred ideas whose blocker may have changed, while
deliberately refusing to turn weak evidence into a recommendation.

The next product layer would be richer evidence connectors and stronger automated
evaluation, but the architecture should remain small: SQLite, deterministic
retrieval/validation, two bounded AI roles, and a source archive that stays under
application control. See [docs/RECONSIDERATION_RADAR.md](docs/RECONSIDERATION_RADAR.md).
