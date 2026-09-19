# Before/after evaluation of the four fixes — 2026-09-19

Method: the real API (in-process) on **isolated copies** of `data/` (never the repo's own
instance for destructive work), old code = `git archive HEAD`, new code = working tree. Answers
were judged against ground truth read directly from `data/source/`, not against the bot.
LLM output varies run to run, so anything that mattered was repeated (3×).

## What changed

| # | Fix | Where |
|---|---|---|
| 1 | Teams `Guest N` captions are their own anonymous speaker (never a person) | `core/anonymous_labels.py`, `ingestion/parsers/transcript.py` |
| 2 | Enumerative questions ("every figure", "how did it change") get a wide pass: 30 fused hits, a per-document-capped list, 12 context seeds, the later-evidence sweep on by default, and a coverage pass on the reasoner's own `search_terms` followed by one re-analysis | `retrieval/text.py`, `retrieval/service.py`, `reasoning/service.py`, `reasoning/prompts.py` |
| 3 | Reviewed `Kwame` (FIRST_NAME) and spoken employee number (VARIANT) aliases in the manifest, so a purge takes them too. The source files themselves were **not** edited: the employee-number line is redacted at purge time only. | `data/source/reviewed_identities.json` |
| 4a | Draft wording is not "what was signed": prompt rules 10–11 plus a deterministic validator cap (HIGH→MEDIUM + note) | `reasoning/prompts.py`, `validation/receipt_validator.py` |
| 4b | Conflicting values: Skeptic `CONFLICTING_VALUE` strategy, a risk trigger for any claim stating a value, prompt rule 12 | `reasoning/skeptic.py`, `reasoning/risk.py`, `reasoning/prompts.py` |
| 4c | Added during evaluation: Skeptic `SOURCE_RELIABILITY` strategy, and a deterministic backstop that forces one for "how reliable…" questions | `reasoning/skeptic.py` |

The real `data/app.db` was re-ingested (2,517 → 2,534 units: 17 guest turns no longer merged
into other speakers; 2,534 embeddings). Backup was taken first.

## Results

| Question | Before | After | Verdict |
|---|---|---|---|
| **T1** who said "Could we change the shape?" / "cannot carry a date" | both lines attributed to Tomas Lindholm (guest text was inside his unit) | Tomas asked; `Guest 1` said the second; "name not established" | **Fixed** |
| **P7** purge Kwame Boateng (scratch copy) | full name/email/phone/initials gone; bare `Kwame` ×13 and the employee number survived | 0 of everything in source, DB rows, FTS, WAL; verifier all zeros; P1 still answerable | **Fixed** |
| **P4** UAT sign-off | opens "Yes", scope quoted as "the signed scope" at HIGH | opens "No — not as asked"; scope at MEDIUM; "executed attachment not in archive" | **Fixed** |
| **P8 / T4** retention 12 vs 18 months | P8 missed the 18-month email entirely; T4 listed both but headline said 18 | P8 status CONFLICTING_EVIDENCE with both values; T4 both surfaced (2/2), headline sometimes still leads with 18 | **Fixed**, headline weak |
| **P5** shelf-life figures | 2 figures (48%, 61%) | "maybe half" (2024), 48% workshop + 48%/4,214 email, "mostly empty", "part of range", 61% current with scope caveat | **Improved** |
| **P6** bakery over time | timeline stopped at Apr 2026 | full descope trail incl. 16 Jun 2026 "in build with Meridian", truncation respected | **Improved** |
| **T2** every waste figure + reliability | 7/7 figures; extract-vs-till reliability finding cited 2/2 | 7/7 figures every time; reliability finding cited **0/3**, then **1/3** with `SOURCE_RELIABILITY`, then **3/3** with the deterministic backstop | **Regressed, then recovered** |
| **T3** delivery plan over time | crisp 2-delivery answer | richer (one-delivery dispute, Lena vs Marco) but noisy, and 2/2 runs wrongly say the 15 Dec go-live is "not established" (the 22 Dec weekly says "Live since 15 December"; that unit is not retrieved) | **Mixed** |
| **T5** SOW wording | INSUFFICIENT_EVIDENCE (already good) | same, plus the draft note | **Unchanged** |
| **P3** op-ID | Nov 2025 only | identical — still misses the Sep 2024 origin ("Then let us take it out") and the 17 Nov call | **Not addressed** (not enumerative) |
| **P9** | good | good | **Unchanged** |

## Critical findings

* **The wide pass is expensive.** Wide questions take ~1.5–3.7× longer (T2 71→129 s, T3 19→72 s,
  P1 37→84 s) because of the second Primary call. It is only triggered by enumerative wording, but
  a judge asking "how did X change" will wait ~1 minute.
* **Wide retrieval helped by finding more, and hurt by finding less by accident.** In T2 the old
  code found the extract-vs-till evidence only *incidentally* (the Skeptic went looking for the
  3.2%/240 t figures in the same document). Once the first pass found those figures itself, the
  incidental route closed. The reliability caveat is now found deliberately, but it shows that
  finding "what undermines this source" is still search luck for any question that doesn't say
  "reliable".
* **Rule 11 ("Not as asked") over-fires.** The first version applied it to what/list questions
  (P1). It is now limited to yes/no questions about a broad thing, but is prompt-level only.
* **T3's false "not established" is a recall miss, not a reasoning one**: the reasoner was right
  about the evidence it had. The later-evidence sweep does not reach a one-line weekly status.
* **Purge leaves the other people in the same unit alone**: the employee-number line also states a
  *different* person's number. That is out of scope for a Kwame purge and stays.
* **P3 still misses the September 2024 origin.** This needs a "who first proposed" recall path;
  none of the four fixes touches it.
* The old-vs-new comparison uses the same isolated database content except for the re-parse, so
  T1's improvement is attributable to the parser alone.

## Tests

390 backend tests pass (new tests cover guest labels, the guest-turn parse, enumerative routing,
the wide pass, coverage spread, the value-risk trigger, the draft-wording cap, both Skeptic
strategies, and the purge of a spoken employee number), ruff clean, frontend typecheck clean.
