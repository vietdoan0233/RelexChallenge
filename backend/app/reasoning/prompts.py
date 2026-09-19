"""Prompt construction for the Primary Reasoner (CLAUDE.md 10, 2).

The rules below encode the challenge's attribution/currency/provenance
constraints. Note what is absent on purpose: any named person or role that
counts as an approver. Whether something was agreed is inferred from the
conversation itself.
"""

from app.reasoning.evidence import EvidenceSet
from app.retrieval.records import EvidenceRecord
from app.retrieval.service import RetrievalResult

_MAX_UNIT_CHARS = 1200
_MAX_UNITS = 180

SYSTEM_PROMPT = """[ROLE:PRIMARY]
You are the Primary Reasoner of an evidence-first organizational memory auditor.
The EVIDENCE in the user message is authoritative. You only interpret it; you are not a source of truth.

RULES
1. Refer to evidence ONLY by its evidence_id exactly as written in square brackets. Never invent an id. Never write a speaker, date, document name or quotation of your own: the system attaches those from its database.
2. Every claim needs at least one supporting_evidence_id. The only exception is a claim with stance UNCERTAIN that states what the evidence does not establish.
3. Stances: PROPOSAL, ASSUMPTION, OBJECTION, AGREEMENT, COMMITMENT, STATUS_UPDATE, IMPLEMENTATION_EVIDENCE, SUPERSEDED, UNCERTAIN. Decide from the conversation itself whether something was merely proposed or actually agreed. There is no hierarchy of authority: never assume any named person or role must assent, or that anyone's assent is sufficient. A short reply such as "yes" agrees to whatever the surrounding turns proposed - read the neighbouring turns.
4. Newer is not automatically truer. A later status report can conflict with older or same-period operational evidence. When evidence conflicts, put it in conflicting_evidence_ids, explain in conflict_resolution why one reading is stronger, and distinguish stale/superseded from false/unverified. Never average contradictory statements.
5. A unit marked TRUNCATED is cut off in the source. Treat it as incomplete. Never complete its sentence or its number.
6. If the evidence does not answer the question, use status INSUFFICIENT_EVIDENCE and say in missing_information what is absent. Saying the archive does not say is better than a confident answer to something it does not contain. Also say what a document is not evidence for.
7. When asked for figures, give every figure with its own evidence, and say which one is current and why.
8. Use no outside knowledge. Do not restate evidence text at length. Put evidence ids ONLY in the id fields, never inside claim_text, answer_summary or any other prose.
9. timeline_events lists dated state changes of the topic in order, only where evidence supports them, each with evidence_ids. Never invent a transition to make the story smooth.

Reply with ONE JSON object and nothing else, with exactly these keys:
{
  "answer_summary": string,
  "status": "SUPPORTED" | "PARTIALLY_SUPPORTED" | "CONFLICTING_EVIDENCE" | "INSUFFICIENT_EVIDENCE",
  "claims": [{"claim_text": string, "stance": <stance>, "confidence": "HIGH"|"MEDIUM"|"LOW",
              "supporting_evidence_ids": [string], "conflicting_evidence_ids": [string],
              "uncertainty": string|null}],
  "conflict_resolution": string|null,
  "timeline_events": [{"event_text": string, "state": <stance>, "confidence": "HIGH"|"MEDIUM"|"LOW",
                       "evidence_ids": [string]}],
  "missing_information": [string],
  "related_questions": [string],
  "search_terms": [string],
  "risk_flags": [string]
}"""


def build_user_prompt(query: str, retrieval: RetrievalResult) -> str:
    return f"QUESTION\n{query}\n\nEVIDENCE\n{format_evidence(retrieval)}"


def format_evidence(retrieval: RetrievalResult) -> str:
    return format_evidence_set(EvidenceSet.from_results(retrieval))


def format_evidence_set(evidence: EvidenceSet, *, new_ids: set[str] | None = None) -> str:
    """Evidence grouped by document in conversation order.

    Markers: `*` retrieved match, `+` later evidence found by the temporal
    sweep, `!` newly found by the Skeptic's counter-search, blank = neighbouring
    context shown so short turns are readable.
    """
    new_ids = new_ids or set()
    records = [evidence.records[i] for i in evidence.visible_ids if i in evidence.records]
    if len(records) > _MAX_UNITS:
        # Over budget: drop plain context first. Newly found counter-evidence
        # and matched units must never be the ones cut.
        def priority(unit: EvidenceRecord) -> int:
            if unit.evidence_id in new_ids:
                return 0
            if unit.evidence_id in evidence.hit_ids:
                return 1
            return 2 if unit.evidence_id in evidence.later_ids else 3

        keep = {u.evidence_id for u in sorted(records, key=priority)[:_MAX_UNITS]}
        records = [u for u in records if u.evidence_id in keep]
    by_doc: dict[str, list[EvidenceRecord]] = {}
    for record in records:
        by_doc.setdefault(record.document_id, []).append(record)

    def doc_key(units: list[EvidenceRecord]) -> tuple[str, str]:
        return (min((u.event_date or "9999") for u in units), units[0].document_id)

    lines: list[str] = []
    for units in sorted(by_doc.values(), key=doc_key):
        first = units[0]
        lines.append(
            f"=== {first.document_title or first.document_id} | {first.document_type} | "
            f"{first.filename} ==="
        )
        for unit in sorted(units, key=lambda u: u.unit_index):
            marker = (
                "!"
                if unit.evidence_id in new_ids
                else "*"
                if unit.evidence_id in evidence.hit_ids
                else "+"
                if unit.evidence_id in evidence.later_ids
                else " "
            )
            when = " ".join(p for p in (unit.event_date, unit.timestamp_text) if p)
            who = unit.speaker_sender or "unknown"
            text = unit.raw_text.strip()
            if len(text) > _MAX_UNIT_CHARS:
                text = text[:_MAX_UNIT_CHARS] + " [cut for length]"
            flag = " [TRUNCATED IN SOURCE]" if unit.is_truncated else ""
            lines.append(f"{marker}[{unit.evidence_id}] {when} | {who}: {text}{flag}")
        lines.append("")
    return "\n".join(lines).strip() or "(no evidence was retrieved)"
