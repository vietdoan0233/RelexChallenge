# KEEPER — Evidence-First Organizational Memory Auditor

*"KEEPER" is a temporary project codename, not a frozen brand — the final
product will use a different name. Runtime surfaces read `APP_NAME` /
`VITE_APP_NAME` (see `.env.example`) rather than hardcoding it; see
`CLAUDE.md`/`AGENTS.md` section 0.4 for the branding-neutrality rule.*

KEEPER is an AI organizational memory auditor built for the RELEX Solutions
"Memory With a Receipt" challenge at AaltoAI Hackathon 2026. It answers
questions over a small enterprise archive by retrieving evidence, reasoning
over it with an LLM, adversarially checking high-risk conclusions with a
Skeptic role, and validating every citation against the database before it
reaches the UI. The full architecture and implementation contract lives in
[CLAUDE.md](CLAUDE.md); this file only covers running the project.

**Status:** Phase 1 Evidence Locker implemented; identity hardening is
complete (25 people / 39 aliases against the real archive, all previously
identified false identities confirmed absent — see `CLAUDE.md` section 0.1).
Phase 1 remains paused at its mandatory review gate because the
organizer-provided GPT API adapter must still be finalized and real
embeddings must still be generated before Phase 2 retrieval begins. See
`CLAUDE.md` section 0.1 for the current checkpoint (`docs/HANDOFF_2026-09-19.md`
is an earlier, now-superseded snapshot) and `CLAUDE.md` section 24 for the
frozen phase plan.

## Archive

`data/source/` holds the canonical, application-owned copy of the challenge
archive: 20 email threads, 2 report threads, and 23 meeting transcripts (45
documents, ~57,000 words, March 2024 – July 2026) about the fictional
retailer Acme Org. `data/ARCHIVE_README.md` and `data/PRACTICE_QUESTIONS.md`
are the archive's own documentation and practice evaluation questions —
useful for building the retrieval benchmark and evaluation tests, not
themselves evidence to ingest.

## Backend setup

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

Copy `.env.example` to `.env` at the repo root. `.env.example` is intentionally
tracked because it contains safe placeholders; `.env` is gitignored and is the
only place where real credentials belong. Leave the GPT fields empty until the
organizers provide the API key, endpoint, and model details.

```bash
uvicorn app.main:app --reload --port 8000
```

## Frontend setup

```bash
cd frontend
npm install
npm run dev -- --port 3000
```

## Tests / lint

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

## Ingestion

From the repository root, deterministic ingestion can run without API access:

```bash
backend/.venv/Scripts/python.exe scripts/ingest.py --skip-embeddings
```

The organizer GPT transport is currently an explicit placeholder. Continue to
use `--skip-embeddings` until the organizers provide the API contract. Once the
adapter is implemented and `GPT_API_KEY`, `GPT_BASE_URL`, and
`GPT_EMBEDDING_MODEL` are configured in the gitignored root `.env`, omit the
flag to generate real vectors:

```bash
backend/.venv/Scripts/python.exe scripts/ingest.py
```

Do not treat semantic retrieval as ready until the ingestion report confirms
real embedding rows for the intended corpus.
