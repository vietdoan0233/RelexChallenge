"""Provider boundary for the reasoning model.

Two roles exist (Primary Reasoner and conditional Skeptic) and both go
through this one narrow interface, so the transport can be swapped or
faked without touching reasoning logic. Requests carry evidence text, so
nothing here ever logs prompts, responses, or keys -- status and request
id only (CLAUDE.md 4, 26).
"""

import logging
import time
from collections.abc import Callable
from typing import Protocol

import httpx

from app.core.errors import AnalysisUnavailableError

_LOGGER = logging.getLogger(__name__)


class LLMClient(Protocol):
    model_name: str

    def complete_json(self, *, system: str, user: str) -> str:
        """Return the model's raw reply, expected to be one JSON object."""
        ...


class OpenAICompatibleChatClient:
    """Chat-completions transport for an OpenAI-compatible organizer service.

    Bounded retries with backoff for transient failures only; every failure
    surfaces as AnalysisUnavailableError with a generic message.
    """

    _TRANSIENT_STATUS_CODES = frozenset({408, 425, 429})

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        initial_retry_delay_seconds: float = 0.5,
        request: Callable[..., httpx.Response] = httpx.post,
    ) -> None:
        if not api_key or not base_url or not model_name:
            raise ValueError("complete API key, base URL, and model are required")
        self.model_name = model_name
        self._api_key = api_key
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._delay = initial_retry_delay_seconds
        self._request = request

    def complete_json(self, *, system: str, user: str) -> str:
        body = {
            "model": self.model_name,
            # No `temperature`: the organizer's reasoning model accepts only
            # its default and rejects an explicit value with HTTP 400.
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        for attempt in range(self._max_retries + 1):
            try:
                return self._once(body)
            except _Transient:
                if attempt == self._max_retries:
                    break
                time.sleep(self._delay * (2**attempt))
        raise AnalysisUnavailableError("the reasoning service is temporarily unavailable")

    def _once(self, body: dict) -> str:
        try:
            response = self._request(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self._timeout,
            )
        except httpx.RequestError as exc:
            _LOGGER.warning("reasoning transport failure error_type=%s", type(exc).__name__)
            raise _Transient from exc

        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        _LOGGER.info(
            "reasoning response status=%s request_id=%s",
            response.status_code,
            request_id or "missing",
        )
        if not response.is_success:
            if response.status_code in self._TRANSIENT_STATUS_CODES or response.status_code >= 500:
                raise _Transient
            raise AnalysisUnavailableError("the reasoning service rejected the request")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AnalysisUnavailableError(
                "the reasoning service returned an unusable reply"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise AnalysisUnavailableError("the reasoning service returned an empty reply")
        return content


class _Transient(Exception):
    pass


class ScriptedLLM:
    """Offline stand-in that replays canned replies, for tests. Like the mock
    embedding provider, it keeps the reasoning path testable with no network
    access or API key."""

    model_name = "scripted-llm-v1"

    def __init__(self, replies: list[str] | list[Callable[[str, str], str]]) -> None:
        self._replies = list(replies)
        self.calls = 0

    def complete_json(self, *, system: str, user: str) -> str:
        self.calls += 1
        reply = self._replies[min(self.calls, len(self._replies)) - 1]
        return reply(system, user) if callable(reply) else reply


class RoleRoutedLLM:
    """Offline stand-in that answers by reasoning role (Primary, Skeptic plan,
    Skeptic verdict, Reconcile), read from the [ROLE:...] tag each system
    prompt starts with. Records the order of roles so tests can assert which
    stages ran. An unscripted role fails loudly."""

    model_name = "role-routed-llm-v1"

    def __init__(self, replies: dict[str, str | Callable[[str, str], str]]) -> None:
        self._replies = replies
        self.roles: list[str] = []

    def complete_json(self, *, system: str, user: str) -> str:
        role = system.split("[ROLE:", 1)[1].split("]", 1)[0]
        self.roles.append(role)
        if role not in self._replies:
            raise AssertionError(f"no scripted reply for role {role}")
        reply = self._replies[role]
        if isinstance(reply, Exception):
            raise reply
        return reply(system, user) if callable(reply) else reply
