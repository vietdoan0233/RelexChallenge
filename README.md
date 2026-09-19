# Organizational Memory Auditor

This project is our solution to the RELEX Solutions **“Memory With a Receipt”** challenge at the AaltoAI Hackathon 2026.

The temporary internal codename is **KEEPER**. It is only a project name; the final product name has not been chosen. The application can use a different display name through `APP_NAME` and `VITE_APP_NAME`.

**Status:** Phase 1 Evidence Locker is complete: all 45 documents ingest into
2,517 stable Evidence Units, FTS has 2,517 rows, and the runtime database has
2,517 real 1,536-dimensional embeddings. The completed gate is documented in
[`docs/PHASE_1_REVIEW_2026-09-19.md`](docs/PHASE_1_REVIEW_2026-09-19.md).
Phase 2 retrieval is complete (see [`docs/PHASE_2_REVIEW_2026-09-19.md`](docs/PHASE_2_REVIEW_2026-09-19.md)); run `python scripts/benchmark.py` to reproduce its benchmark. Phase 3 (structured Cases and the validator) is complete — see [`docs/PHASE_3_REVIEW_2026-09-19.md`](docs/PHASE_3_REVIEW_2026-09-19.md); Phase 4 (risk routing, Skeptic, reconciliation) is complete — see [`docs/PHASE_4_REVIEW_2026-09-19.md`](docs/PHASE_4_REVIEW_2026-09-19.md); Phase 5 (deletion/anonymization) is complete with disclosed deviations — see [`docs/PHASE_5_REVIEW_2026-09-19.md`](docs/PHASE_5_REVIEW_2026-09-19.md); Phase 6 (the judge-facing UI) is complete — see [`docs/PHASE_6_REVIEW_2026-09-19.md`](docs/PHASE_6_REVIEW_2026-09-19.md); Phase 7 is next. `docs/HANDOFF_2026-09-19.md` is an earlier,
superseded snapshot; use `CLAUDE.md` section 0.1 and section 24 for the current
phase plan.

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
- what happens to the memory if a person’s data is deleted.

The archive is intentionally small enough to inspect, but complicated enough to expose these problems:

- 45 evidence documents;
- 20 email threads;
- 2 report threads;
- 23 meeting transcripts;
- approximately 57,000 words;
- dates from March 2024 to July 2026; and
- conversations about the fictional retailer **Acme Org**.

The judges can ask questions that we have not seen beforehand. They can also request the deletion of a person’s data while watching whether the system really removes that person from its stored memory and recalculates affected conclusions.

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

The latest verified ingestion produced **2,517 Evidence Units**:

- 2,115 transcript units;
- 110 email-message units; and
- 292 report units.

The parser keeps useful context with each unit, including the source document, date, speaker or sender, thread context, timestamp text, and the original wording.

### 3. We preserve the source instead of “correcting” it

The archive contains intentionally incomplete statements. For example, a sentence or number may end abruptly. The parser records that a unit is truncated instead of guessing how the sentence should have ended.

The archive also contains anonymous `Me:` / `Them:` conversations. We preserve those labels and do not pretend to know who those people really are. A person mentioned inside an anonymous conversation can still be recorded as mentioned, but the anonymous speaker is not silently assigned to that person.

Known transcript formatting noise, repeated interface text, and image placeholders are handled with deterministic rules. The purpose is to remove obvious export clutter without changing the meaning of the original statement.

### 4. Evidence IDs remain stable

Each Evidence Unit receives a stable identifier and a source locator. The locator acts like a permanent address inside the original document. If a person’s material is removed later, the remaining evidence should not receive confusing new addresses or accidentally bring deleted material back during a rebuild.

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

Real people found only in text are added through a human-reviewed identity file, `data/source/reviewed_identities.json`. Short forms such as first names, last names, initials, nicknames, and spelling variants are also added only when explicitly reviewed. A name being unique in the archive is not enough by itself.

This conservative rule protects the deletion feature. If the system mistakenly turns an ordinary phrase into a person, it could later erase or hide unrelated organizational memory.

### 6. Keyword search is ready

The Evidence Locker has an SQLite full-text search index containing **2,517 rows**, one for each Evidence Unit. This gives us a dependable offline way to find evidence using words from the user’s question.

We have also created a provider-neutral embedding interface. Embeddings are numerical summaries that help find passages with similar meaning even when they do not use exactly the same words. The interface is ready, and tests use a deterministic local mock, but real embeddings are not yet available because the organizer-provided GPT service details have not been supplied.

### 7. Ingestion can be rerun safely for development

The ingestion process can rebuild the derived evidence tables from the canonical source. It validates the source files and reviewed identity file before clearing rebuildable data. People and aliases are regenerated from the sanitized inputs so stale or false identities do not live forever in the database.

The source-locator manifest is kept separately so normal rebuilding does not renumber old source locations. This is the foundation needed for reliable future deletion and recalculation.

### 8. The basic application scaffold exists

The backend has a FastAPI health/configuration scaffold and a SQLite database/repository layer. The frontend has a React, Vite, TypeScript, and Tailwind scaffold with configurable neutral branding.

The current frontend is intentionally only a starting screen. The full Case page, evidence receipts, Decision Evolution view, and privacy page are future build phases.

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
| Real GPT embedding generation | Waiting for organizer API details |
| Primary question answering | Not started |
| Semantic retrieval and hybrid retrieval | Not started as a real production path |
| Skeptic and risk-based checking | Not started |
| Case UI and Decision Evolution | Not started |
| Personal-data deletion/anonymization | Designed, not implemented |
| Project Pulse | Optional future work; not started |

The current quality gate is **71 passing backend tests**, clean Ruff checks, and a successful frontend typecheck/build. Phase 0 is complete. Phase 1 is implemented enough to pause at its required review gate, but we should not call the system “semantic retrieval ready” or start Phase 2 until real embeddings have been generated and checked.

## What remains before the next phase

The immediate remaining Phase 1 work is:

1. Configure a local `.env` without committing secrets.
2. Receive and implement the organizer-provided GPT endpoint, authentication, and request/response contract.
3. Run one real embedding smoke test.
4. Generate real embedding rows for the intended 45-document corpus.
5. Rerun the complete Phase 1 checks and record the final review.

After that, Phase 2 can implement retrieval, structured reasoning, conflict handling, receipts, and the Case UI.

The privacy requirement is important but is not secretly finished. The target design is to remove or irreversibly anonymize a requested person from every application-owned surface while preserving unrelated organizational facts where possible. That includes source files, database text, names and metadata, search indexes, embeddings, cached answers, and generated artifacts. A whole Evidence Unit is deleted only when a smaller redaction would still leave the person identifiable. This work belongs to a later phase and currently has no purge implementation.

## Running the project locally

### Backend setup

The backend uses Python 3.11 or newer.

```bash
cd backend
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
# source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy `.env.example` to `.env` at the repository root. The real `.env` is ignored by Git and is the only place for credentials. Leave the GPT fields empty until the organizers provide the API key, endpoint, and model details.

Start the backend with:

```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend setup

```bash
cd frontend
npm install
npm run dev -- --port 3000
```

### Run the current offline ingestion

From the repository root, the parser and Evidence Locker can be rebuilt without network access:

```bash
backend/.venv/Scripts/python.exe scripts/ingest.py --skip-embeddings
```

The command parses the archive, rebuilds the evidence tables, creates the full-text search index, links people to evidence, and prints an ingestion report. The `--skip-embeddings` option is for offline development without credentials.

The organizer service is verified as OpenAI-compatible at `/v1/embeddings` (bearer authentication, `{model, input}` requests, numeric vectors in the response). With `GPT_API_KEY`, `GPT_BASE_URL`, and `GPT_EMBEDDING_MODEL` configured in the gitignored root `.env`, real vectors can be generated with:

```bash
backend/.venv/Scripts/python.exe scripts/ingest.py
```

Do not claim semantic retrieval is ready until the ingestion report confirms real embedding rows for the intended corpus.

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

## Innovation roadmap

After the core phases are complete, Phase 7 includes a small, precomputed
**Reconsideration Radar** demonstration. It surfaces previously rejected or
deferred ideas whose original blocker may have changed, while keeping internal
evidence, external signals, assessment, and missing information separate. The
feature is deliberately bounded: it says only **worth reassessing**, never that
the organization should pursue an idea. See
[docs/RECONSIDERATION_RADAR.md](docs/RECONSIDERATION_RADAR.md).
