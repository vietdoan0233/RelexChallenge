# Phase 1 Review — Evidence Locker

## Result

**Passed.** The Evidence Locker is ready for Phase 2 retrieval.

## Corpus and ingestion evidence

| Check | Verified result |
| --- | --- |
| Evidence documents | 45: 23 transcripts, 20 email threads, 2 report threads |
| Evidence Units | 2,517: 2,115 transcript, 110 email, 292 report |
| FTS rows | 2,517 |
| Parse warnings | None reported |
| Stable-ID sample | `EV-01_2024-03-20_solution-demo-value-workshop-t64` |
| Anonymous evidence | 138 `Me`/`Them` units remain anonymous |
| Truncated evidence | 3 units are preserved and flagged |

The stable locator manifest, including transcript turn locator `t64` in the
sample above, is the evidence-ID source. It is independent of the current
ordinal position of a unit.

## Identity and attribution evidence

| Check | Verified result |
| --- | --- |
| People | 25 |
| Aliases | 39: 25 full names, 14 email aliases |
| Relations | 402 AUTHOR, 1,964 SPEAKER, 242 MENTIONED |
| Unresolved alias candidates | 72, deliberately left unmerged |
| Rejected free-text candidates | 50, never added as people or aliases |

The reviewed identity manifest supplies the nine text-only identities. No
short-form alias is promoted without explicit human review.

## Embedding evidence

The configured HTTPS OpenAI-compatible `/v1/embeddings` contract first passed
a one-text smoke test. After explicit approval to send the archive, a full
isolated ingestion succeeded and its verified derived database was installed as
the runtime `data/app.db` artifact.

| Check | Verified result |
| --- | --- |
| Real embedding rows | 2,517 |
| Models represented | 1 configured embedding model |
| Vector dimension | 1,536 for every row |
| Values | Every stored value is finite |
| Batch behavior | Bounded batches, transient retry, per-batch savepoint |
| Prompt/response persistence | No raw prompt or provider response persisted |

`data/app.db` is gitignored. The application-owned canonical source remains
`data/source/`; it was not modified during embedding generation.

## Quality gate

```text
backend: 131 passed
ruff: clean
frontend typecheck: passed
frontend production build: passed
```

The test process emitted two dependency deprecation warnings from
FastAPI/Starlette's test client. They do not affect Phase 1 behavior.

## Phase 2 handoff

Phase 2 may now implement lexical BM25 retrieval, semantic cosine retrieval,
deterministic rank fusion, neighbor context expansion, and later-evidence
sweeps. Its exit gate remains a benchmark showing relevant evidence near the
top for at least ten known topics.
