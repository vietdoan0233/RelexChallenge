# Phase 7 Review — Hardening and Reconsideration Radar

## Result

**Core hardened; Radar implemented and verified live, with one shortfall against
its MVP target (below).** This completes the planned build.

## Part 1 — Core hardening

Practice questions were run live through the full pipeline (real retrieval,
real model, scratch database) and checked for invariants (valid receipts, no
fabricated ids, hedging where the archive is silent):

| Question | Outcome |
| --- | --- |
| P1 master-data assessment, Sept 2024 | **Found a real miss**: `INSUFFICIENT_EVIDENCE` although the 2024-09-24 workshop held the figures. Fixed (below); now `SUPPORTED` with 48 %, 31 %, 4,214 / 1,317 / 3,105 and their source documents |
| P2 ordering service levels | `PARTIALLY_SUPPORTED`, hedged (the agreed value is not preserved) |
| P3 operator-ID attribution | `SUPPORTED`, deep-checked |
| P4 UAT sign-off | `SUPPORTED`, names the signer and the excluded scope |
| P5 shelf-life proportions | Four dated figures; 61 % is current **for three categories only**; refuses to generalise |
| P6 bakery over time | Dated timeline; current state is a separate workstream |
| P7 erase a person | Verified end to end in the UI and on real-archive copies (Phase 5/6) |
| P8 agreed-then-never-done | Honest partial: retention period agreed, later changed; no one evidenced as responsible |
| P9 "extract completed, no errors" | Answers what the reports are evidence for and not for |

The P1 fix added two deterministic retrieval behaviours: a named month or year
now adds a period-restricted ranked list, and a question asking for
"figures / proportions / rates" also searches `percent`. New benchmark topic
ranks first; the other twelve are unchanged (hybrid: 11/13 in the top 5, 13/13
in the reasoner-visible set).

Other hardening evidence already in place: malformed and fenced model output,
provider failure and retries, insufficient evidence (no model call), retrieval
degradation to lexical-only, deletion rehearsal, and cache/index reset.

## Part 2 — Reconsideration Radar

Built (`backend/app/radar/`, `api/radar.py`, `scripts/radar.py`, UI **Radar**):

- Discovery in four focused passes (rejection, deferral, constraint-blocked,
  "revisit/wait until"), each candidate requiring validated evidence for the
  proposal, the outcome **and** the blocker, else dropped.
- Per candidate: later-evidence sweep, assessment, real counter-retrieval, then a
  Skeptic verdict on the **seven checks**. Checks 1 (not genuinely rejected) and 7
  (obsolete) reject a candidate; a skipped check counts as unanswered.
- A deterministic guard: only the four allowed assessments; a changed-condition
  claim needs a receipt or is lowered to `INSUFFICIENT_EVIDENCE`; check 4/6
  failures lower the assessment; overreaching wording (should / recommend /
  advise / approve / "go for it" …) is withheld or dropped; budget/owner/approval
  are always listed as unestablished; ids are stripped from prose.
- Each finding is a `pulse_findings` row (`RECONSIDERATION_CANDIDATE`, ids and
  short prose only) linked to a **validated Case** and to `finding_evidence` rows.
- Internal evidence, external signals and the assessment render as three
  visibly different blocks on the Finding Card; every citation opens the evidence
  drawer; "Open the validated Case" links through.
- Deletion: findings and their linked Cases are invalidated by evidence
  dependency **and** by a text scan for the person's identifiers.

### Exit criteria

| Criterion | Status |
| --- | --- |
| Explicit proposal + blocker for every candidate | Met (validated ids; tested) |
| Every changed-condition claim has a receipt | Met (guard + tests) |
| External vs internal visibly separated | Met (schema, card, UI) |
| No wording stronger than "worth reassessing" | Met for the Radar's own voice; `proposal`/`blocker` describe past statements and are constrained by prompt and receipts, not by the guard |
| Missing budget/owner/approval displayed | Met |
| Skeptic can reject a false candidate | **Met live**: rejected an obsolete phased-rollout candidate on real data |
| Findings link to a validated Case + Evidence Units | Met |
| Deleting a person invalidates findings and Cases | Met (tested) |
| A candidate surfaced before the user asks | Met: the Radar page opens with precomputed findings |

### Shortfall — stated plainly

The MVP asks for **3–5** findings. Live runs surfaced **1–2** each time (all
`STILL_BLOCKED`, plus 1 Skeptic rejection), and discovery varies run to run
because the organizer model is non-deterministic. No candidate was assessed
`WORTH_REASSESSING` or `PARTIALLY_CHANGED` in any live run, so that path is
proven by tests but has not been shown on real data. `data/source/external_signals.json`
ships **empty on purpose**: I will not invent outside developments, so no external
signal has been exercised outside tests. If you want a stronger demo, curate a few
real signals there and re-run `scripts/radar.py`.

## Quality gate

```text
backend: 351 passed   ruff: clean
frontend: typecheck passed, oxlint clean, build passed
```

Haiku reviewers: the auditor and a red-team tester converged on real gaps
(regex coverage, `monitorable_condition` unguarded, skipped Skeptic checks);
all were fixed and tested. Findings of theirs I did not adopt: a blanket guard
on `proposal`/`blocker` (they legitimately quote past "should" statements) and a
"content vs claimed outcome" validator (that judgement is Skeptic check 1).
A bug of my own was caught by the new tests (a rejection reason and a finding id
were both strings).

## Known risks

- Live Radar and Case output are non-deterministic.
- Radar recall depends on the model's discovery; expect few candidates.
- `external_signals.json` is app-owned but the sanitizer does not rewrite it; if
  it ever names a removed person, verification fails closed rather than editing it.
