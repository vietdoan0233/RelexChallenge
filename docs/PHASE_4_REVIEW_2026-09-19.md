# Phase 4 Review — Risk Routing, Skeptic, Reconciliation

## Result

**Passed.** Decision, agreement and current-state questions are routed to deep
checking deterministically; the Skeptic performs real counter-retrieval and
introduces newly retrieved counter-evidence; the Primary reconciles; the
validator stays the last step. Phase 5 (deletion/anonymization) may begin.

## What was built

| Module | Role |
| --- | --- |
| `reasoning/risk.py` | Small named ruleset (no numeric score): question language (agreed / decided / approved / signed off / commitment / fulfilled / current / superseded / who), conflicting evidence, ambiguous stance, medium/low confidence, single supporting unit, later evidence, >90-day date spread, disagreeing source types, status report vs other sources, no claims. The model's confidence can only escalate scrutiny |
| `reasoning/skeptic.py` | Plan ≤ 2 counter-search bundles (`DIRECT_CONTRADICTION`, `ALTERNATIVE_STATE`, `LATER_IMPLEMENTATION`, ≤ 3 short queries each) → run through the same `RetrievalService` (temporal sweep for alternative/later strategies) → inspect only the new evidence → objections citing ids |
| `reasoning/reconcile.py` | Primary reconciliation over initial answer + objections + new evidence; no separate polish stage |
| `reasoning/evidence.py` | Union of evidence any model was shown; the validator accepts only ids in it. Counter-search contributions are bounded (top 5 hits + windows + top 3 later evidence per query) |
| `service.py` | Routes, degrades safely, records a `ReviewInfo` (risk level and triggers, Skeptic attempted, queries, units examined, objections, reconciled, completed) |

Behaviour worth stating plainly:

- Call budget: low risk = 1 model call; high risk ≤ 4 (Primary, plan, verdict,
  reconcile). The verdict call is skipped when counter-search surfaces nothing
  new, and reconciliation is skipped when the Skeptic finds no objection —
  a latency guard (CLAUDE.md 13.1) that deviates from "always reconcile".
- A failure in the Skeptic or reconciliation never yields an unchecked
  confident answer: the result is marked `completed=false`, confidence is
  capped at MEDIUM, status drops from SUPPORTED, and a provisional note is added.
- Deletion dependencies: only counter-evidence the Skeptic **relied on** is
  recorded in `case_evidence` (usage `CONFLICT`); units merely surfaced by a
  search are counted, not recorded, or almost any deletion would invalidate
  almost every Case.

## Verification

Deterministic (fake role-routed model, real retrieval): indirect replacement
with different vocabulary is found where a direct-negation search misses it;
bundle/query caps; reconciliation cannot cite evidence no model saw;
Skeptic/reconcile failure → provisional; malformed verdict → incomplete;
counter-evidence recorded as a dependency; deleted counter-evidence vanishes
from a served Case; over-budget prompts never drop newly found evidence.

Live (real retrieval, real model), practice questions:

| Question | Result |
| --- | --- |
| P3 operator-ID attribution | `SUPPORTED`, deep-checked, 0 rejected ids, ~21 s |
| P6 bakery over time | `SUPPORTED`, dated timeline, current state = separate workstream, ~30 s |
| P9 "extract completed, no errors" | `CONFLICTING_EVIDENCE`; answers what the reports are evidence for (job ran, file landed) and what they are not (contents checked/reconciled), ~22 s |
| Planted wrong candidate ("bakery is part of Fresh") | Skeptic planned 6 queries in different vocabulary, examined 58 new units, raised a HIGH objection citing the Nov 2025 descoping evidence; reconciliation corrected the answer to "No — descoped, now a separate workstream" |

On P3/P6/P9 the Skeptic raised no objection because the initial answers were
correct; the planted-candidate run is what shows it can find contradicting
evidence live.

## Quality gate

```text
backend: 271 passed
ruff check / ruff format --check: clean
frontend typecheck: passed
```

Haiku reviewers: the auditor found one real defect (a 180-unit prompt cap could
cut newly found counter-evidence) — fixed by bounding counter-search
contributions and truncating plain context first, with tests. The adversarial
tester, this time required to execute probes, reported three defects; on
inspection they came from probe queries that matched no evidence (so the model
was correctly never called) and one claim already covered by an existing
passing test. Explicit regression tests were added for the malformed-verdict and
invalid-shape cases; one genuine gap surfaced by that work (`skeptic_ran` stayed
false when the Skeptic failed midway) was fixed.

## Known risks carried forward

- Live answers are not deterministic (the organizer model accepts only its
  default `temperature`).
- Risk triggers are keyword/rule based; a question phrased without any cue and
  answered with HIGH-confidence, multi-source claims takes the single-pass path.
- The skip-reconciliation optimisation means "Skeptic found nothing" answers
  are not re-read by the Primary.
- Counter-search recall still depends on the model's query vocabulary.
- The transcript dial-in-number parser flaw from Phase 3 is unchanged (filed).
- Phase 5 must invalidate `cases`/`case_evidence` and scrub FTS
  `thread_context` / `speaker_sender`.
