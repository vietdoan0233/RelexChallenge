# Organizational Memory Auditor — Feature Inventory for the Pitch Deck

*RELEX "Memory With a Receipt" challenge · AaltoAI Hackathon 2026 · compiled 2026-09-20 from the code and the running app.*

**One-line pitch:** an evidence-first memory of what an organization actually decided. Every answer comes with a receipt, conflicts are shown instead of averaged away, and a person's identity can be replaced everywhere with a stable alias, without losing their history, and restored only by an authenticated admin.

**The central rule (say this on a slide):** *The Evidence Locker is the memory. The LLM is only an interpreter.* Raw evidence is authoritative; every model output is a derived interpretation that the system re-checks against the stored evidence before showing it.

---

## 0. The archive in numbers (all verified)

| Fact | Value |
|---|---|
| Source documents | **45**: 20 email threads, 2 report threads, 23 meeting transcripts |
| Evidence Units (the atomic, citable pieces) | **2,534**: 2,132 transcript turns, 110 emails, 292 report items |
| Time span | March 2024 – July 2026 |
| Participants identified | 24 in a fresh ingest |
| Embeddings | 1,536-dimensional, one per Evidence Unit |
| Automated tests | **490 passing** (backend) |
| LLM providers | One OpenAI-compatible endpoint (organizer-provided); nothing else required to run keyword search offline |

---

## 1. Ask — questions that open a Case, not a chat

**What it is.** A search box on the home page. Every question opens or creates a **Case**: a structured, validated ruling with support, conflicts, uncertainty and sources. It is deliberately not a chat bubble stream.

- **Case, not chat.** The answer is a typed object (status, claims, timeline, missing information, related questions), and the UI renders only validated fields. There is no free-text "make it pretty" pass, so the model cannot add unsourced prose on the way to the screen.
- **Example questions** as one-click chips (pricing, vendor approval, Q2 plan, open risks).
- **Live "thinking" screen** with coarse progress states while a Case is analysed (analysing evidence, checking for contradictions, reconciling current state), so a high-risk answer feels like a deliberate audit rather than a stalled page.
- **Recent Cases** list on the home page: status chip (Completed / In progress), claim count, age, one-click reopen. **View all** expands to the last 30. A repeated question is listed once (its latest Case).
- **Archive statistics** on the home page and an "Archive ready" indicator in the header (documents, evidence units, people, date range).
- **Interactive particle background** behind the hero (particles.js): hover pulls nearby particles toward the cursor, a click adds particles. Decorative only; skipped for visitors who ask their system for reduced motion.
- **Honest failure.** If the reasoning service is down or returns invalid output, the user sees an explicit error and keeps their question; nothing is fabricated.

---

## 2. Retrieval — finding the right evidence without sending the whole archive

The archive is small, so the design is deliberately simple and inspectable (no vector database, no framework).

- **Hybrid search:** SQLite **FTS5 with BM25** for words, plus **embedding cosine similarity** (NumPy, in memory) for meaning.
- **Reciprocal Rank Fusion** merges the two rankings deterministically; no learned re-ranker to tune or explain away.
- **Neighbour context:** every high-ranked unit is returned with the smallest coherent exchange around it, so "yes" or "sounds good" arrives together with what was being agreed to. The window is computed deterministically and is bounded so it can never grow to a whole document.
- **Temporal sweep:** for questions about the current state, final decision, latest agreement, supersession or history, a later-evidence pass searches for what happened *after* the first hit. It is a retrieval step, not a claim that newer means truer.
- **Wide pass and coverage re-analysis** for questions that ask for a list ("which decisions…").
- **Benchmark:** a 12-topic retrieval benchmark; the relevant evidence is in the fused top 5 for 10 of 12 topics and top 10 for 11 of 12, and in the reasoner-visible set for all 12.
- **Lexical also indexes** thread context and speaker/sender, so a short reply ("Received, thank you.") is still findable through its thread title.

---

## 3. The reasoning pipeline — an interpreter that has to show its work

```
question → hybrid retrieval → Primary Reasoner → candidate claims
        → deterministic risk rules
        → low risk:  direct receipt
        → higher risk: Skeptic → counter-retrieval → reconciliation
        → deterministic validator → Case
```

### 3.1 Primary Reasoner
- Returns **structured candidate claims**, not prose: claim text, stance, confidence, supporting and conflicting evidence IDs, uncertainty, missing information, timeline events.
- Cites evidence **by ID only**. It is never trusted for speaker, date, document name or quote.
- **Nine stances** separate what people actually did: *proposal, assumption, objection, agreement, commitment, status update, implementation evidence, superseded, uncertain*.
- **No hardcoded authority.** Nobody is ever coded as "the approver". Whether something became a decision is inferred from the conversation itself.
- Truncated source sentences (the corpus contains deliberately cut-off statements) are treated as incomplete evidence and never completed.

### 3.2 Deterministic risk engine
- A small, explainable rule set, not a fake 0–100 score, and not the model's own confidence.
- Forces deep checking for words like *agreed, decided, approved, signed off, current, ultimately, superseded, who authorized…* and for structural triggers: conflicting evidence, evidence across very different dates, source types that disagree, a status report contradicting operational evidence, only one weak source, medium/low confidence.
- The Case shows **why** it received the scrutiny it did.

### 3.3 Conditional Skeptic (real counter-retrieval)
- Its only job is to **find evidence that would make the answer wrong**, and it must run new searches, not just critique.
- Plans up to **two** counter-search bundles per Case, each with a *different* strategy out of five:
  1. **Direct contradiction**: explicit rejection, cancellation, reversal, non-approval.
  2. **Alternative / replacement state**: e.g. the claim says Kafka was chosen, so it searches for RabbitMQ, migration or a later broker choice.
  3. **Later implementation**: what was actually shipped, escalated, deferred or worked around afterwards.
  4. **Conflicting value**: same attribute, different number, date or owner in another document (e.g. a "12-month retention" vs other stated figures).
  5. **Source reliability**: a figure derived from an extract or report that itself was never reconciled.
- Results come back as objections with severity and the newly found evidence IDs.

### 3.4 Reconciliation
- The Primary Reasoner revises its answer against the objections. Contradictions are **never averaged**: the conflict is surfaced, one reading is explained as stronger, and uncertainty is preserved. If the archive cannot settle it, the status is *insufficient evidence*, with what is known and what is missing.

### 3.5 Deterministic validator (the trust boundary)
- Every cited evidence ID must exist, must have been visible to the model, must not be deleted, and must belong to a real document.
- **Fabricated IDs are rejected and never rendered.** A claim with no valid support is dropped or downgraded, not shown with a fake citation.
- All displayed citation metadata (speaker, date, document, thread, exact text) is **hydrated from the database**; the model cannot override it.
- The Case shows how many citations were removed, if any.

---

## 4. The Case view — what a judge actually sees

- **Verdict header:** the question, a status pill (*Supported / Partially supported / Conflicting evidence / Insufficient evidence*) and the answer.
- **How this was checked:** risk level, whether the Skeptic ran, whether counter-evidence was examined, and notes, plus an optional step-by-step trace of the pipeline.
- **Objections raised** by the check (with severity), when there are any.
- **Claim cards:** each claim with its verdict, stance, confidence, its **supporting sources** and any **conflicting evidence**, each source a one-click row (title, speaker/filename, date).
- **How conflicting evidence was weighed:** the written resolution when the archive disagrees with itself.
- **Decision Evolution** (the standout feature): see §5.
- **What the archive does not establish:** an explicit list of what is missing.
- **Case summary rail:** status, created time, claim and source counts, Case ID, and actions (View sources, Compare over time, Ask follow-up, Save / export via print).
- **Related questions:** one click asks a follow-up.
- **Copy link / print** controls; Case URLs are shareable.

### 4.1 Evidence drawer ("open any receipt")
- Opens the **cited unit highlighted**, with the surrounding conversation marked as *Context*, so an isolated "yes" is understandable.
- Shows document, date, speaker/sender, thread context and the exact stored text. Truncated source text is labelled as cut off, never completed.
- Speaker and sender names inside citations are **clickable participant profiles** (§8.3).

---

## 5. Decision Evolution — how the organization's position changed

- A horizontal, dated timeline of the states the evidence supports (proposed → agreed → contradicted → superseded → current).
- **Every node has evidence** and opens it; nodes carry the date, the stance, and a short label plus description.
- **Ambiguous transitions stay ambiguous.** Missing steps are never invented to make a smooth story, and "current" is a reasoned conclusion, not simply the newest statement.
- Newer is not automatically truer: a recent status report can be contradicted by operational evidence, and the timeline shows both.

---

## 6. Reconsideration Radar — the proactive feature

**Idea:** surface ideas the organization *rejected or deferred* where the original blocker may have changed, so valuable ideas do not stay buried. The system tells you what to look at before you ask.

- Finds **explicitly rejected or deferred** proposals only. An open question, an unactioned objection or a plan that simply went ahead does not count.
- Each finding is a card: the original proposal, **why it was stopped**, **what may have changed**, and **still unknown**, each with its own source link, plus the Case it links to.
- **Four assessments only**: *worth reassessing, partially changed, still blocked, insufficient evidence*. It never says "you should do this".
- **Internal evidence, external signals and the assessment are kept visibly separate**: external signals come from a curated file and are labelled as outside the organization; the assessment is labelled an interpretation, not evidence.
- **Seven Skeptic checks** per finding (genuinely rejected? blocker actually stated? hidden secondary blocker? does the change address the blocker? is the external source credible? recent evidence against reopening? obsolete for another reason?), each shown as pass / counts against / cannot be answered.
- Findings are **precomputed** so the page opens with answers waiting; each links to a validated Case (no free-floating AI findings).
- Summary chips count findings per assessment; a side panel explains each assessment type and offers "Turn hindsight into progress" (an example question).

---

## 7. Add data — growing the archive

- **Upload .txt emails, meeting/conversation transcripts and reports** (type selector, multi-file picker, drag and drop, selected-file list, per-file problems shown inline).
- Files are **staged, parsed with the real parser, then saved into the canonical source**, then the archive is rebuilt from it. Uploaded documents get the same stable evidence IDs as the original archive and appear in the database, the search index, embeddings, retrieval and the statistics.
- **Success only after the database confirms it.** On any failure the request's files are removed and the user sees exactly why.
- Safety: `.txt` only, size and file-count limits, path-traversal and unsafe filenames rejected, empty or binary files rejected, a duplicate name gets a unique suffix and **never overwrites**, refused while a privacy operation is running, one ingestion at a time.
- Only **new** units are embedded; existing vectors are reused. With no embedding service the upload still succeeds (keyword-searchable) and says clearly that embeddings were skipped.
- **Recent ingestions** table: real documents, type, item count, indexed / keyword-only status, added time; **View all** expands it.
- *Connect sources* tiles (Gmail, Outlook, Drive, Teams, Notion) are shown as a preview only and are labelled as not enabled in this build; nothing is fetched automatically.

---

## 8. Privacy — pseudonymisation with a full history, and a controlled way back

This is the deletion requirement done as **robust pseudonymisation**: the organization's evidence and a person's complete history survive, while the person's identity does not appear on any ordinary surface.

### 8.1 What pseudonymisation does
- Every participant has a **random internal ID**, a stable **cryptographically random alias** (e.g. `Participant 6T3D-2M`) and a state (**Active / Pseudonymised**). Aliases are never derived from a name, hash or sequence, and stay the same across rebuilds.
- Pseudonymising a person **rewrites the application-owned canonical source** to their alias everywhere it identifies them: speaker lines, email headers and sender addresses, recipients, attendee lists, signatures, meeting titles and inline mentions, plus the identity manifest.
- **Nothing is deleted.** Every Evidence Unit, evidence ID and relationship (author / speaker / mentioned) survives, so their complete history stays inspectable under the alias, and the ID stays stable.
- Dependent Cases, receipts, timeline events and Radar findings are **invalidated and recalculated** from the alias-bearing evidence; the search index and embeddings are regenerated so no old text survives.

### 8.2 Strict name-to-person assignment (new)
- **"Ana Duarte" and "Ana" are the same person.** Assignment works on two bases, full name and first name, through one shared resolver used by ingestion linking, the pseudonymisation target and verification, so they can never disagree.
- A bare first name is assigned to a participant, and rewritten with their full name, **only if** it is unique across everyone's name parts, at least three letters, not an everyday word, and not a reserved label. A first name shared by two people (the two **Nadias**) is **never guessed**: it is left unchanged and the console tells the operator why.
- On the real archive, **22 of 24 first names** are assigned safely (for example Ana's 14 bare mentions and Kwame's 13 are now covered); both Nadias are refused. A bare speaker line like "Ana" resolves to the one Ana Duarte instead of creating a second person.
- A first name a human reviewed into the identity file stays authoritative.
- Verification is consistent with the rewrite: a bare name counts as a leak only as a whole word, so "ana" is not a false alarm inside "management" or "analysis". E-mail addresses and multi-word names keep strict substring checks.

### 8.3 Universal, clickable participant profiles
- Every speaker, sender, mention, citation and timeline node is a link to that participant's profile.
- **Active profile:** real name, counts (authored, spoken, mentioned), and the **full history**: every email, meeting and report contribution with the exact quote and an "Open in context" link.
- **Pseudonymised profile:** the alias only, plus non-identifying counts. Never the original name, email or any vault detail, while the history remains complete.

### 8.4 The Privacy console
- **Choose a participant:** search, per-person authored/spoken and mentioned counts with a bar, a *Pseudonymised* badge, and a profile shortcut.
- **Review the impact:** units they wrote or spoke, units that mention them, files to rewrite, dependent Cases to invalidate; the alias they will receive; and which first name will (or will not) be rewritten and why.
- **Authorize:** a four-step guide (Choose → Review → Authorize → Verified). The action needs the **admin token**, which is never stored and is sent only in the request's Authorization header.
- **Live progress** through the stages (lock, rewrite source, rebuild, refresh embeddings, verify).
- **Result:** per-surface scan counts (source files, filenames, database rows and search index, database file/WAL/journal, artifacts and cache, vault directory) and preservation checks (marked pseudonymised, alias stable, original name cleared, original aliases removed, every relationship preserved). It distinguishes **verified** from **complete, embeddings pending** (see §9) instead of a false alarm.
- **What gets verified** panel and re-ask suggestions after an operation ("ask again" questions that did not mention the person).

### 8.5 Reversal — the controlled way back (new in the UI)
- Pseudonymised participants appear in the same console. Selecting one opens **Reverse pseudonymisation**: what reversal does, an **explicit confirmation checkbox**, the admin token, then a Reverse button that stays disabled until both are given.
- Reversal **decrypts the identity from the vault**, restores it in the source, search index and embeddings, and verifies every surface. It has its own progress stages, result view (files restored, embeddings) and a "Back to the console" button.
- The original identity is only ever available through this **separately authenticated admin workflow**, never through profile, search, evidence or case views.
- Disclosed limit: reversal restores every position to the vault's one canonical name, so a bare "Ana" that was rewritten comes back as "Ana Duarte".

### 8.6 The safety machinery behind it
- **Encrypted, isolated reversal vault:** authenticated encryption, stored in a separate file, key supplied outside the database, source, cache and logs. A normal database connection has no path to it.
- **Fail-closed admin auth:** an unset admin token means every request is unauthorized. `confirm=true` alone is never treated as authorization.
- **Staged, crash-safe operation:** exclusive lock, a durable resumable plan containing only IDs, paths, alias and counts (never the original name), atomic file replacement, recovery by recorded state on restart. A failed operation leaves the archive locked and never reports success.
- **Read/write gate:** the archive does not answer questions while a privacy operation is running; the UI says so.
- **No-store headers** on personal-data responses and a cache-clearing header after operations.
- **Audit record** (subject ID, alias, states, timestamps, counts, verification result) that never contains the original name.
- **Verification is a fail-closed backstop:** any tracked identifier surviving in the source, database, search index, database file/journal, artifacts or cache fails the operation. Even a filename that literally contains the name fails it.

---

## 9. Trust, quality and engineering

- **Provenance you can click:** every claim points to stored evidence; display fields come from the database, not the model.
- **Stable Evidence IDs:** derived from document plus a persistent locator, so deleting or rewriting one unit never renumbers the others, and IDs survive pseudonymisation, reversal and rebuild.
- **Fine-grained Evidence Units** (one speaker turn, one email, one report bullet) so a person's or a fact's footprint is small and precise.
- **Parsers built for a messy corpus:** named Teams transcripts (UI chrome and duplicated caption text removed, consecutive fragments merged only when clearly one turn), anonymous `Me:` / `Them:` transcripts left anonymous, `Guest N` speakers kept as their own anonymous speaker, truncation preserved and flagged, many image-placeholder variants handled, multi-language email headers (English, German, Swedish) parsed.
- **Identity hardening:** free-text capitalized phrases can never become a person; short forms enter the alias table only through a human-reviewed manifest, and the manifest is validated *before* any destructive rebuild.
- **Offline-capable:** the whole ingestion, keyword search and profile stack runs without any API key; embeddings and reasoning are the only parts that need the provider. A provider failure produces a clear report, not a corrupted archive.
- **Non-blocking embeddings:** if the embedding service is unreachable, privacy operations still complete and verify, and the result shows how many embeddings are pending.
- **Test-driven privacy:** destructive tests only ever run against temporary copies; the real source and database are never touched by tests.
- **490 automated tests**, plus linting, type checking and a production build.
- **Consistent design system:** one white-and-blue theme, Figtree typography, matched to the reference mockups.

---

## 10. Suggested demo flow (about 4 minutes)

1. **Ask** a decision question ("Did Acme sign off UAT, and what exactly was the scope?"). Show the Case status, *How this was checked*, a claim with a conflict, and the **Decision Evolution** timeline.
2. **Click a source** to open the evidence drawer with the cited unit highlighted in context. Click a speaker name to reach their **profile and full history**.
3. **Radar:** show one finding with its original proposal, blocker, what may have changed, and the seven checks.
4. **Add data:** upload a new email and immediately search for a phrase from it.
5. **Privacy:** pick a participant, show the impact preview and the first-name note (Ana unique vs the two Nadias left alone), authorize with the admin token, watch the stages, then the verified result.
6. **Re-ask the same question** to show the Case recomputed under the alias while the history is intact; open the pseudonymised profile.
7. **Reverse** it: select the participant in the console, confirm, authorize, and show the identity restored and verified.

---

## 11. Honest limits (put these in the notes, judges will ask)

- Pseudonymised records **remain personal data**. This is not irreversible anonymisation, cryptographic erasure, or a legal compliance claim. The "EU privacy controls" label in the header is a product label, not a certification.
- Verification is **application-level**: it checks the identifiers the system tracks across storage it owns. It cannot prove an untracked nickname never existed.
- **Reversal cannot tell which short form stood where**; it restores the canonical full name.
- A first name shared by two people is **deliberately not rewritten**, so a bare "Nadia" can remain visible after either Nadia is pseudonymised.
- **Authentication is one admin bearer token**, not user accounts or sessions. The profile chip in the header is a placeholder and is labelled as such.
- **Connectors** (Gmail, Outlook, Drive, Teams, Notion) are not built; upload of `.txt` files is the real ingestion path.
- Radar findings are **precomputed**, not live-updating.
- While a privacy operation runs, the archive **locks** and cannot answer questions.
- Semantic search needs the embedding service; without it, keyword search still works and the UI says so.
- Retrieval has known misses on some questions (see the phase reviews); the design mitigates them with the Skeptic and by showing "insufficient evidence" rather than guessing.
