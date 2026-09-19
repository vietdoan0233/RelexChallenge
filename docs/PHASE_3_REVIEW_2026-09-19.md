# Phase 3 Review — Primary Reasoner, Receipts, Validator

## Result

**Passed.** A question now flows retrieval → Primary Reasoner → deterministic
validator → DB-hydrated Case, over both the Python API and HTTP. Phase 4
(risk routing, Skeptic, reconciliation) may begin.

## Organizer reasoning contract (verified, not assumed)

A benign fixed-prompt probe (no archive content) established:

- OpenAI-compatible `POST {GPT_BASE_URL}/chat/completions`, bearer auth.
- `response_format: {"type": "json_object"}` works.
- The model rejects an explicit `temperature` (HTTP 400, only its default is
  accepted), so the client sends none. Output is therefore not fully
  deterministic; tests fake the model instead of depending on it.

## What was built

| Module | Role |
| --- | --- |
| `schemas/reasoning.py` | What the model may emit: claims, stance, confidence, evidence **ids only**. No field for speaker/date/document/quote; unknown keys are ignored |
| `schemas/receipt.py` | Ids-only `ValidatedReceipt` (persisted) and DB-hydrated `CaseReceipt` / `EvidenceView` (served) |
| `reasoning/llm.py` | Provider boundary: `OpenAICompatibleChatClient` (timeout, bounded retry, status + request-id logging only) and an offline `ScriptedLLM` |
| `reasoning/prompts.py` | Rules from CLAUDE.md 2/10 (no authority hierarchy, newer ≠ truer, truncation, insufficient evidence). Evidence grouped by document with hit / later / context markers and a TRUNCATED flag |
| `reasoning/primary.py` | Structured call, one schema-repair retry, then a controlled `AnalysisUnavailableError` |
| `validation/receipt_validator.py` | Rejects unknown or non-visible ids, drops unsupported claims, caps confidence on truncated-only support, sorts the timeline, strips ids from prose, hydrates every citation from the DB |
| `reasoning/service.py` | `CaseService.answer` / `load_case_receipt`, id-only trace |
| `api/cases.py`, `api/evidence.py` | `POST /api/cases/query`, `GET /api/cases/{id}`, `GET /api/evidence/{id}` (cited unit + neighbour context) |

Design choices worth knowing:

- Stored Cases hold **ids only**. `cases.receipt_json` contains no evidence text,
  and every read re-validates ids against the database, so a unit deleted after
  a Case was stored cannot render (the claim is dropped; status falls to
  `INSUFFICIENT_EVIDENCE`).
- With no retrieved evidence the model is not called at all.
- Model failure is an explicit HTTP 503, never an invented answer.
- No new dependency; no agent framework.

## Live verification (real retrieval + real model)

Run on a scratch copy of the database (deleted afterwards), practice questions:

| Question | Status | Notes |
| --- | --- | --- |
| P2 ordering service levels | `PARTIALLY_SUPPORTED` | Hedged correctly: the agreed value is not preserved in the excerpts; 0 rejected ids |
| P4 UAT sign-off | `SUPPORTED` | Named the signer and quoted the excluded scope; separated the January sign-off from later steering-report language; 0 rejected ids |

Two live observations led to changes: the model placed `[EV-…]` in prose, so the
prompt now forbids it and the validator strips it; and an auditor-found gap
(prose that was *only* an id fell back to the raw text) was fixed and tested.

## Quality gate

```text
backend: 234 passed
ruff check / ruff format --check: clean
frontend typecheck: passed
```

Haiku reviewers: the codebase auditor found one real defect (id-only prose
fallback), fixed. The adversarial tester's report read as static analysis
rather than executed probes, so it is not counted as independent execution
evidence; the equivalent cases (fabricated / non-visible / duplicate ids,
extra keys, fenced or malformed JSON, deleted evidence, injection-like text)
are covered by the repository's own tests instead.

## Known risks carried forward

- **Parser flaw (Phase 1):** a dial-in participant shown only by phone number
  leaks into neighbouring unit text in one transcript
  (`07_2024-11-12_ordering-logic-design`, 3 units) and their own turns are lost.
  Filed as a separate task; fixing it changes unit boundaries and needs a
  re-ingest, which re-sends the archive to the embedding provider and therefore
  needs your approval.
- Retrieval sees only the question. The Primary's `search_terms` do not yet
  drive a second retrieval pass; Phase 4 adds temporal/counter retrieval.
- No risk routing yet: every Case takes the single-pass path, so
  decision/current-state answers are not yet adversarially checked.
- Model non-determinism (no `temperature` control) means live answers vary run
  to run; invariants, not wording, are what the tests assert.
- Persisted trace/log content is ids and counts only, but Phase 5 must still
  invalidate `cases` / `case_evidence` rows on deletion.

## Phase 4 handoff

`CaseService.answer` is the insertion point: risk engine after `primary.analyze`,
Skeptic + counter-retrieval through the same `RetrievalService`, reconciliation
through the same `LLMClient`, with `validate_primary` staying the final step.
