# Phase 2 Review — Retrieval

## Result

**Passed.** Hybrid retrieval is implemented and benchmarked on 12 known topics.
Phase 3 (Primary Reasoner, receipts, validator) may begin.

## What was built

`backend/app/retrieval/`:

| Module | Role |
| --- | --- |
| `text.py` | Deterministic query analysis: stopwords, light stemming (`committed`→`commit*`, `decided`→`decis*`), temporal-question detection, FTS5-safe quoting |
| `lexical.py` | SQLite FTS5 + BM25; unit text weighted 1.0, thread title and sender 0.4 |
| `semantic.py` | Stored embeddings + NumPy cosine; refuses mixed models, mixed dimensions, malformed or non-finite vectors |
| `fusion.py` | Reciprocal Rank Fusion, `K = 60`, deterministic tie-break |
| `context.py` | ±1 neighbour window; transcripts expand to at most ±3 while turns are context-dependent ("Yes.") |
| `temporal.py` | Later-evidence sweep: same lexical + semantic retrieval restricted to strictly later dates |
| `service.py` | Orchestration, visible-evidence set, id-only trace, visible degradation to lexical-only |
| `records.py` | DB-hydrated evidence records; ids with no row are dropped |
| `benchmark.py` | Topic loader and evaluator used by `scripts/benchmark.py` and the tests |

No new dependency, no learned reranker, no vector database, and no model call
inside ranking.

### Schema change

`evidence_fts` now indexes `thread_context` and `speaker_sender` beside
`raw_text`, so a short email such as "Received, thank you." is findable through
its thread title. FTS is a derived table: `migrations.initialize` upgrades an
old single-column table in place from `evidence_units` without touching
embeddings, and needs no provider call. Row count is unchanged at 2,517.

Phase 5 note: these two FTS columns are now a storage surface that a person
purge must scrub (recorded in `schema.sql`).

## Benchmark (12 topics, real archive)

Hybrid run with the organizer embedding service (only the 12 topic questions
were sent — no evidence text):

| Measure | Result |
| --- | --- |
| Relevant unit in fused top 5 | 10 / 12 |
| Relevant unit in fused top 10 | 11 / 12 |
| Relevant unit in the reasoner-visible set (hits + context + sweep) | 12 / 12 |
| Lexical-only (offline, guarded by a test) | 8 / 12 in top 5, 11 / 12 visible |

Weak topics, reported rather than tuned away:

- `bakery-scope` — fused rank 15. The answer is spread across three documents
  and bakery-titled meetings dominate lexically. It is in the visible set.
- `cutover-runbook` — fused rank 6 (lexical 1, semantic 4).

Relevance is judged on database text (document + pattern), not on hard-coded
Evidence IDs or answers. Topic criteria were corrected against the corpus
during the work (for example the go/no-go topic now names the actual decision
turns); the thread-title weight was left at 0.4 rather than raised to 1.0,
which would have gained one topic while regressing another.

## Quality gate

```text
backend: 194 passed
ruff check / ruff format --check: clean
frontend typecheck: passed
```

Two Haiku reviewers (codebase auditor, adversarial tester) ran read-only. The
auditor found no issues. The tester reproduced one defect — ragged or
malformed stored vectors raised a raw `ValueError` instead of
`SemanticIndexError`, bypassing the lexical fallback — which is fixed and
covered by two new tests.

## Known risks carried forward

- Embeddings were generated from `raw_text` only. Thread-title context helps
  the lexical side but not the semantic side; regenerating context-aware
  embeddings would mean sending the archive to the provider again and needs
  explicit approval. Not done.
- Query→temporal routing is a keyword heuristic. Phase 3's Primary output
  can force the sweep on (`temporal_sweep=True`).
- Some transcripts carry phone-number participants whose UI chrome ("+4",
  "+358 …") merged into unit text during Phase 1 parsing. It does not affect
  ranking noticeably but is visible in evidence text.
- Semantic recall varies by phrasing; several topics rely on lexical to
  recover what semantic misses, and vice versa.

## Phase 3 handoff

`RetrievalService.retrieve()` returns ranked ids, neighbour windows, an
optional later-evidence sweep, DB-hydrated records, and a text-free trace.
`visible_evidence_ids` is the set the validator must require cited ids to
belong to (CLAUDE.md 15).
