"""Primary Reasoner (CLAUDE.md 10).

Turns retrieved evidence into structured candidate claims. Its output is
untrusted until the deterministic validator has checked it.
"""

import json
import logging

from pydantic import ValidationError

from app.core.errors import AnalysisUnavailableError
from app.reasoning.llm import LLMClient
from app.reasoning.prompts import SYSTEM_PROMPT, build_user_prompt
from app.retrieval.service import RetrievalResult
from app.schemas.reasoning import PrimaryOutput

_LOGGER = logging.getLogger(__name__)
# One repair attempt on a schema violation, then fail: bounded, and a
# second failure is a real problem worth surfacing rather than hiding.
_MAX_ATTEMPTS = 2


def analyze(llm: LLMClient, query: str, retrieval: RetrievalResult) -> PrimaryOutput:
    user = build_user_prompt(query, retrieval)
    repair_note = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        raw = llm.complete_json(system=SYSTEM_PROMPT, user=user + repair_note)
        try:
            return PrimaryOutput.model_validate_json(_strip_fence(raw))
        except (ValidationError, ValueError) as exc:
            # Log the failure category only: validation errors can quote the
            # model's (evidence-derived) text.
            _LOGGER.warning(
                "primary output invalid attempt=%s error_type=%s", attempt, type(exc).__name__
            )
            repair_note = (
                "\n\nYour previous reply was not a valid JSON object for the required schema. "
                "Reply again with ONE valid JSON object using exactly the specified keys and "
                f"allowed enum values. Problem locations: {_error_locations(exc)}"
            )
    raise AnalysisUnavailableError(
        "the reasoning service did not return a usable structured answer"
    )


def _strip_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _error_locations(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors()[:8])
    return "not parseable as JSON" if isinstance(exc, json.JSONDecodeError) else "unparseable"
