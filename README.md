# KEEPER — Evidence-First Organizational Memory Auditor

KEEPER is an AI organizational memory auditor built for the RELEX Solutions
"Memory With a Receipt" challenge at AaltoAI Hackathon 2026. It answers
questions over a small enterprise archive by retrieving evidence, reasoning
over it with an LLM, adversarially checking high-risk conclusions with a
Skeptic role, and validating every citation against the database before it
reaches the UI. The full architecture and implementation contract lives in
[CLAUDE.md](CLAUDE.md); this file only covers running the project.

**Status:** Phase 1 Evidence Locker implemented and paused at its mandatory
hardening/review gate. Identity extraction must be tightened and real Gemini
embeddings must be generated before Phase 2 retrieval begins. See
`docs/HANDOFF_2026-09-19.md` for the current checkpoint and `CLAUDE.md`
section 24 for the frozen phase plan.

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

Copy `.env.example` to `.env` at the repo root and fill in `GOOGLE_API_KEY`.

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
ruff check app tests
ruff format --check app tests
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

After configuring `GOOGLE_API_KEY` and `GEMINI_EMBEDDING_MODEL` in the
gitignored root `.env`, omit `--skip-embeddings` to generate real vectors:

```bash
backend/.venv/Scripts/python.exe scripts/ingest.py
```

Do not treat semantic retrieval as ready until the ingestion report confirms
real embedding rows for the intended corpus.
