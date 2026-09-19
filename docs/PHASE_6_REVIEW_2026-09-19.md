# Phase 6 Review — Judge-Facing UI

## Result

**Passed.** The complete flow works in a browser with no developer
intervention: ask a question → open a Case → inspect evidence in context → read
Decision Evolution → remove a person in the Privacy console → confirm the
removal → re-ask. Phase 7 (hardening and Reconsideration Radar) may begin.

## What was built (`frontend/src`)

| Surface | Behaviour |
| --- | --- |
| Ask (`pages/AskPage`) | Free-text question, example questions, recent questions (per-viewer `localStorage`, guarded, cleared after a privacy operation), coarse progress states — Analyzing evidence → Checking for contradictions → Reconciling current state |
| Case (`components/case/CaseView`) | Status → conclusion → review panel (risk level, why it was checked, contradiction-check size, objections, an explicit **provisional** warning when the check could not finish) → claims with stance/confidence/uncertainty and support **and** conflicts → conflict resolution → Decision Evolution → what the archive does not establish → related questions (CLAUDE.md 21 order) |
| Evidence drawer (`components/evidence`) | Cited unit highlighted, neighbouring turns visibly marked *Context*, thread/document/date/speaker/timestamp, the "cut off in the source — not completed" flag; Esc, focus trap, focus restored |
| Decision Evolution (`components/timeline`) | Chronological nodes, each with state, confidence and clickable sources; nothing invented |
| Privacy console (`pages/PrivacyPage`) | Searchable people with unit counts → impact preview (units, files, Cases to invalidate) → typed-name confirmation → staged progress → verification table per surface with the honest scope note |

Rendering rules: the UI only displays API fields; provenance is never
composed client-side. No new dependency (hash router, TanStack Query for data).
The Vite dev server proxies `/api` to the backend.

## Verification (real browser, real model, scratch instance)

The backend was pointed at a **scratch copy** of the database and source, never
the repository's `data/`:

- Bakery-over-time question through the UI: `Supported`, deep check shown ("6 targeted
  searches, 89 new passages"), 9 claims with sources, dated timeline; opening a
  citation showed the highlighted unit with ±context.
- Privacy console for Kwame Boateng: preview 97 units / 18 files / 1 Case →
  confirm gate (button disabled until the exact name is typed) → **verified**,
  every surface `0 — clean`, 20 embeddings regenerated.
- After removal: the dependent Case returns 404; the same question re-asked cites
  no Kwame Boateng, the answer no longer names them, and it states the evidence
  "does not identify every participant" — recalculated from surviving evidence.
  0 occurrences of the name in the response, scratch source, or DB files.
- Mobile 375 px and light mode: no horizontal overflow, readable, touch targets
  ≥ 44 px (the app name link excepted).
- The repository's runtime database and source were unchanged afterwards.

## Quality gate

```text
backend: 312 passed   ruff: clean
frontend: typecheck passed, oxlint clean, production build passed
```

Haiku UI reviewer: confirmed provenance is rendered verbatim and destructive
actions are gated. Two findings were applied (conflict resolution moved below
the claims per the §21 order; drawer focus trap). One was declined on purpose:
re-ask suggestions are filtered by substring of the removed person's name, which
can over-hide a suggestion but never leaks one.

## Known risks

- No frontend test suite exists; UI behaviour was verified in the browser, not by
  automated tests.
- The preview launcher could not start Node in this environment (sandbox
  working-directory error), so Vite was run separately; `.claude/launch.json`
  is unchanged.
- Live answers are non-deterministic, so exact wording differs between runs.
- Per-viewer recent questions can name a person until a privacy operation runs;
  they are cleared then.
