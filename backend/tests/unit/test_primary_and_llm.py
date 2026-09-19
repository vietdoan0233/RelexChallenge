import json
import logging

import httpx
import pytest

from app.core.errors import AnalysisUnavailableError
from app.reasoning import primary
from app.reasoning.llm import OpenAICompatibleChatClient, ScriptedLLM
from app.reasoning.prompts import SYSTEM_PROMPT, build_user_prompt, format_evidence
from app.retrieval.service import RetrievalService

GOOD = json.dumps(
    {
        "answer_summary": "s",
        "status": "SUPPORTED",
        "claims": [
            {
                "claim_text": "c",
                "stance": "AGREEMENT",
                "confidence": "HIGH",
                "supporting_evidence_ids": ["EV-x"],
            }
        ],
    }
)


@pytest.fixture
def retrieval(conn, seed_units):
    seed_units(
        conn,
        "meeting",
        [
            ("Shall bakery stay in the fresh workstream?", "Ana", "2025-01-10"),
            ("Yes.", "Lena", "2025-01-10"),
            ("Bakery is its own workstream now.", "Marco", "2025-06-10"),
        ],
    )
    conn.execute("UPDATE evidence_units SET is_truncated = 1 WHERE unit_index = 2")
    return RetrievalService(conn, None).retrieve("bakery workstream", temporal_sweep=True)


def test_valid_reply_is_parsed(retrieval):
    out = primary.analyze(ScriptedLLM([GOOD]), "q", retrieval)
    assert out.claims[0].supporting_evidence_ids == ["EV-x"]


def test_code_fenced_reply_is_accepted(retrieval):
    out = primary.analyze(ScriptedLLM([f"```json\n{GOOD}\n```"]), "q", retrieval)
    assert out.status.value == "SUPPORTED"


def test_one_repair_attempt_then_success(retrieval):
    llm = ScriptedLLM(["not json at all", GOOD])
    assert primary.analyze(llm, "q", retrieval).answer_summary == "s"
    assert llm.calls == 2


def test_second_invalid_reply_is_a_controlled_error(retrieval, caplog):
    llm = ScriptedLLM(['{"answer_summary": "leaky evidence text", "status": "BOGUS"}'] * 2)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AnalysisUnavailableError) as info:
            primary.analyze(llm, "q", retrieval)
    assert "leaky" not in str(info.value)
    assert "leaky" not in caplog.text
    assert llm.calls == 2


def test_prompt_has_evidence_ids_markers_and_truncation_flag(retrieval):
    text = format_evidence(retrieval)
    assert "[EV-meeting-2]" in text and "[TRUNCATED IN SOURCE]" in text
    assert "*[EV-" in text  # a retrieved hit is marked
    assert "Yes." in text  # neighbouring context is shown so a bare "yes" is readable
    assert "QUESTION\nq?" in build_user_prompt("q?", retrieval)


def test_system_prompt_encodes_the_frozen_rules_and_no_named_authority():
    lowered = SYSTEM_PROMPT.lower()
    assert "no hierarchy of authority" in lowered
    assert "newer is not automatically truer" in lowered
    assert "never complete its sentence or its number" in lowered
    assert "insufficient_evidence" in lowered
    for forbidden in ("approver", "decision maker", "manager must"):
        assert forbidden not in lowered


def test_no_evidence_marker_when_nothing_retrieved(conn, seed_units):
    seed_units(conn, "d", ["hello"])
    empty = RetrievalService(conn, None).retrieve("zzzqqq")
    assert format_evidence(empty) == "(no evidence was retrieved)"


# ------------------------------------------------------------- HTTP client


def _client(handler, **kwargs):
    return OpenAICompatibleChatClient(
        api_key="sk-secret-key",
        base_url="https://llm.example/v1/",
        model_name="m",
        initial_retry_delay_seconds=0,
        request=handler,
        **kwargs,
    )


def _response(status=200, body=None, headers=None):
    return httpx.Response(
        status, json=body, headers=headers, request=httpx.Request("POST", "https://x")
    )


OK_BODY = {"choices": [{"message": {"content": '{"a": 1}'}}]}


def test_client_posts_to_chat_completions_with_bearer_and_json_mode():
    seen = {}

    def handler(url, **kw):
        seen.update(url=url, **kw)
        return _response(200, OK_BODY, {"x-request-id": "req-1"})

    assert _client(handler).complete_json(system="S", user="U") == '{"a": 1}'
    assert seen["url"] == "https://llm.example/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-secret-key"
    assert seen["json"]["model"] == "m"
    assert "temperature" not in seen["json"]
    assert seen["json"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in seen["json"]["messages"]] == ["system", "user"]


def test_transient_failure_is_retried_then_succeeds():
    replies = iter([_response(503), _response(429), _response(200, OK_BODY)])
    assert _client(lambda *a, **k: next(replies)).complete_json(system="S", user="U")


def test_transient_failure_exhausts_retries_into_a_controlled_error():
    calls = []

    def handler(*a, **k):
        calls.append(1)
        return _response(500)

    with pytest.raises(AnalysisUnavailableError):
        _client(handler).complete_json(system="S", user="U")
    assert len(calls) == 3  # 1 + 2 retries: bounded


def test_permanent_failure_is_not_retried():
    calls = []

    def handler(*a, **k):
        calls.append(1)
        return _response(401, {"error": "bad key sk-secret-key"})

    with pytest.raises(AnalysisUnavailableError) as info:
        _client(handler).complete_json(system="S", user="U")
    assert len(calls) == 1
    assert "sk-secret-key" not in str(info.value)


def test_transport_error_is_retried_and_then_controlled():
    def handler(*a, **k):
        raise httpx.ConnectError("boom with evidence text")

    with pytest.raises(AnalysisUnavailableError):
        _client(handler).complete_json(system="S", user="U")


@pytest.mark.parametrize(
    "body", [{}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}, "nonsense"]
)
def test_malformed_reply_is_a_controlled_error(body):
    with pytest.raises(AnalysisUnavailableError):
        _client(lambda *a, **k: _response(200, body)).complete_json(system="S", user="U")


def test_logs_contain_status_and_request_id_only(caplog):
    with caplog.at_level(logging.DEBUG):
        _client(lambda *a, **k: _response(200, OK_BODY, {"x-request-id": "req-7"})).complete_json(
            system="SECRET SYSTEM PROMPT", user="SECRET EVIDENCE TEXT"
        )
    assert "req-7" in caplog.text
    for leaked in ("SECRET SYSTEM PROMPT", "SECRET EVIDENCE TEXT", "sk-secret-key", '{"a": 1}'):
        assert leaked not in caplog.text


def test_incomplete_configuration_is_refused():
    with pytest.raises(ValueError):
        OpenAICompatibleChatClient(api_key="", base_url="https://x", model_name="m")
