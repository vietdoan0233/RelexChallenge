"""Neighbor context expansion (CLAUDE.md 9.4).

A turn like "yes" or "sounds good" is meaningless without the proposal it
answers, so the reasoner and the evidence drawer must see the surrounding
exchange. The window is computed deterministically here rather than left
to the model to cite both sides of every exchange.
"""

import re
import sqlite3
from dataclasses import dataclass

# Turns this short (or opening with a bare assent/dissent) depend on what
# came before or after them to mean anything.
_SHORT_WORDS = 8
_DEPENDENT_OPENERS = re.compile(
    r"^\W*(yes|yeah|yep|no|nope|ok|okay|sure|right|exactly|correct|agreed|fine|"
    r"sounds good|that works|let'?s do that|mm-?hm|good)\b",
    re.IGNORECASE,
)

BASE_RADIUS = 1
# Bounded so a run of short turns cannot grow the window to the whole document.
MAX_RADIUS = 3


@dataclass(frozen=True)
class ContextWindow:
    anchor_id: str
    document_id: str
    # Evidence ids in document order, including the anchor.
    unit_ids: tuple[str, ...]

    @property
    def context_ids(self) -> tuple[str, ...]:
        """Neighbours only -- context, not independently cited support."""
        return tuple(i for i in self.unit_ids if i != self.anchor_id)


def is_context_dependent(text: str) -> bool:
    return len(text.split()) <= _SHORT_WORDS or bool(_DEPENDENT_OPENERS.match(text))


def expand(conn: sqlite3.Connection, anchor_ids: list[str]) -> list[ContextWindow]:
    windows = []
    for anchor_id in dict.fromkeys(anchor_ids):
        window = _window_for(conn, anchor_id)
        if window is not None:
            windows.append(window)
    return windows


def _window_for(conn: sqlite3.Connection, anchor_id: str) -> ContextWindow | None:
    anchor = conn.execute(
        "SELECT e.document_id, e.unit_index, e.raw_text, d.document_type "
        "FROM evidence_units e JOIN documents d ON d.document_id = e.document_id "
        "WHERE e.evidence_id = ?",
        (anchor_id,),
    ).fetchone()
    if anchor is None:
        return None

    # Only spoken turns are conversational fragments; an email or report
    # unit is already a self-contained message, so +-1 is enough there.
    dynamic = anchor["document_type"] == "TRANSCRIPT"
    radius = BASE_RADIUS
    index = anchor["unit_index"]
    while True:
        rows = conn.execute(
            "SELECT evidence_id, unit_index, raw_text FROM evidence_units "
            "WHERE document_id = ? AND unit_index BETWEEN ? AND ? ORDER BY unit_index",
            (anchor["document_id"], index - radius, index + radius),
        ).fetchall()
        if not dynamic or radius >= MAX_RADIUS:
            break
        anchor_needs_more = radius < 2 and is_context_dependent(anchor["raw_text"])
        edges = [r for r in (rows[0], rows[-1]) if r["unit_index"] != index]
        edge_needs_more = any(is_context_dependent(r["raw_text"]) for r in edges)
        # Stop once the window's edges are self-explanatory or the document ends.
        if not (anchor_needs_more or edge_needs_more) or (
            rows[0]["unit_index"] > index - radius and rows[-1]["unit_index"] < index + radius
        ):
            break
        radius += 1

    return ContextWindow(
        anchor_id=anchor_id,
        document_id=anchor["document_id"],
        unit_ids=tuple(r["evidence_id"] for r in rows),
    )
