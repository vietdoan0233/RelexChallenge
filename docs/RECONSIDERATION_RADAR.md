# Reconsideration Radar

## Status

Planned innovation extension for Phase 7. This is not part of the frozen core
query path and must not delay the Phase 1 review or the Phase 2–6 core exits.

## Product promise

Reconsideration Radar answers a proactive question:

> Which previously rejected or deferred ideas may be worth reassessing because
> the reason for saying no may have changed?

It must never claim that the organization should pursue an idea. Its outcome is
limited to:

- `STILL_BLOCKED`
- `PARTIALLY_CHANGED`
- `WORTH_REASSESSING`
- `INSUFFICIENT_EVIDENCE`

The user decides what to do next.

## Why this is useful

Organizations often preserve the outcome of a decision but lose the conditions
that produced it. A proposal rejected because of capacity, cost, timing,
technology, security, regulation, or missing data can remain buried after those
conditions change. Reconsideration Radar turns that forgotten history into a
small, inspectable list of candidates for human review.

## Evidence boundaries

Every finding keeps four lenses separate:

1. **Internal evidence** — the original proposal, rejection/deferment, blocker,
   and current internal state.
2. **External signal** — a curated or later-provided publication, regulation,
   market signal, technology update, or other outside development.
3. **Assessment** — a bounded interpretation of whether the signal addresses the
   blocker; it is not a company fact.
4. **Missing information** — facts the archive cannot establish, such as a new
   budget, security review, owner, or delivery estimate.

External signals must never be silently promoted to internal organizational
truth. A finding is allowed to say that a condition may have changed; it is not
allowed to say that a proposal is approved, funded, safe, or strategically right
without internal evidence.

## Candidate pipeline

```text
explicit proposal
    ↓
rejected / deferred outcome
    ↓
original blocker with evidence
    ↓
blocker translated to a monitorable condition
    ↓
new internal evidence and/or curated external signal
    ↓
Skeptic validation
    ↓
validated Case + Reconsideration Radar finding
```

Initial blocker categories:

- capacity or required effort,
- cost or vendor availability,
- timing or dependency,
- technology maturity,
- security or compliance,
- regulation,
- insufficient internal data.

## Skeptic gate

No finding is surfaced until the Skeptic checks:

1. Was the proposal genuinely rejected or deferred?
2. Was the displayed blocker actually stated in the evidence?
3. Is there a hidden or secondary blocker?
4. Does the new signal directly address the original blocker?
5. Is the external source credible and verifiable?
6. Does recent internal evidence argue against reopening?
7. Has the proposal become obsolete for a different reason?

If a check cannot be answered, the card must show that as missing information.

## Hackathon MVP

Implement a small, precomputed demonstration set:

- identify 3–5 proposals with explicit rejected/deferred language;
- extract the original blocker and evidence receipt;
- map each blocker to one monitorable condition;
- pair candidates with a small curated signal set and recent internal evidence;
- run the Skeptic checks;
- store each result as a `pulse_findings` row with category
  `RECONSIDERATION_CANDIDATE` and link it to a validated Case;
- render the Finding Card and an evidence drawer.

Do not add recurring web scraping, notifications, automatic task creation, or
an external integration during the hackathon.

## Finding Card contract

```text
RECONSIDERATION CANDIDATE

Original proposal:       [internal evidence]
Original outcome:        REJECTED | DEFERRED
Why it was stopped:      [internal evidence]
What may have changed:   [internal and/or external evidence]
Assessment:              STILL_BLOCKED | PARTIALLY_CHANGED |
                          WORTH_REASSESSING | INSUFFICIENT_EVIDENCE
Unestablished:           [missing internal facts]
Next useful check:       [bounded human validation step]
```

Every factual line must open its source receipt. Assessment and uncertainty
must be visually distinct from evidence.

## Implementation placement by phase

- **Phase 1:** no Radar code; make sure source locators, identities, and
  Evidence IDs are trustworthy.
- **Phase 2:** reuse hybrid retrieval, context expansion, and later-evidence
  sweeps to find proposals, blockers, and changes.
- **Phase 3:** represent the Radar result as a validated Case/Receipt rather
  than free-floating generated prose.
- **Phase 4:** reuse the Skeptic for the seven checks and adversarial searches.
- **Phase 5:** include Radar findings, linked Cases, and cached external signals
  in invalidation and deletion verification.
- **Phase 6:** add a Radar view, Finding Card, evidence drawer, and “what
  changed?” comparison to the judge-facing UI.
- **Phase 7:** precompute the 3–5 demo findings, run red-team tests, and make
  the feature the final initiative story.

## Exit criteria

Reconsideration Radar is complete only when:

- every surfaced candidate has an explicit original proposal and blocker;
- every changed-condition claim has an internal or external receipt;
- external signals and internal facts are visibly separated;
- no finding uses language stronger than `worth reassessing` without new
  internal evidence;
- missing budget, owner, security, cost, or approval information is displayed;
- the Skeptic can reject a false candidate;
- each finding links to a validated Case and Evidence Units;
- deleting a person invalidates any affected Radar finding and its cache;
- the demo can show at least one candidate that was surfaced before the user
  asked about it.
