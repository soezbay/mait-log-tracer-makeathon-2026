"""KI:connect provider: OpenAI-style API at https://chat.kiconnect.nrw/api/v1 (no network in tests)."""
from __future__ import annotations

import json

import httpx
import pytest
from fixtures import build
from helpers import good_submission
from openai import OpenAI

from logtracer.assistant.agent import SUBMIT_SPEC, LogTracerAgent
from logtracer.assistant.config import Settings
from logtracer.assistant.data_access import LogStore
from logtracer.assistant.providers import ProviderError, create_provider
from logtracer.assistant.providers.kiconnect import DEFAULT_BASE_URL, KIConnectProvider
from logtracer.assistant.tools import TOOL_SPECS

ALL_TOOLS = [*TOOL_SPECS, SUBMIT_SPEC]


class FakeServer:
    """A KI:connect stand-in: records requests, answers from a script."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, request.headers, body))
        status, payload, headers = self.replies.pop(0)
        return httpx.Response(status, json=payload, headers=headers)

    def client(self) -> OpenAI:
        return OpenAI(api_key="kic-test", base_url=DEFAULT_BASE_URL, max_retries=0,
                      http_client=httpx.Client(transport=httpx.MockTransport(self)))


def completion(content=None, calls=()):
    tool_calls = [{"id": f"call_{i}", "type": "function",
                   "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(calls)]
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return (200, {"id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": "dep",
                  "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
                  "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}}, {})


def error(status, code, message, headers=None):
    return (status, {"error": {"message": message, "type": "x", "param": None, "code": code}}, headers or {})


def test_settings_build_the_provider_with_clear_errors():
    with pytest.raises(ProviderError, match="KICONNECT_API_KEY"):
        create_provider(Settings(_env_file=None, llm_provider="kiconnect", llm_model="dep"))
    with pytest.raises(ProviderError, match="--list-models"):
        create_provider(Settings(_env_file=None, llm_provider="kiconnect", KICONNECT_API_KEY="k"))
    p = create_provider(Settings(_env_file=None, llm_provider="kiconnect", llm_model="dep",
                                 KICONNECT_API_KEY="k"))
    assert p.name == "kiconnect" and p.model == "dep"
    assert str(p.client.base_url).rstrip("/") == DEFAULT_BASE_URL
    other = create_provider(Settings(_env_file=None, llm_provider="kiconnect", llm_model="dep",
                                     KICONNECT_API_KEY="k", kiconnect_base_url="https://x.example/api/v1"))
    assert str(other.client.base_url).rstrip("/") == "https://x.example/api/v1"


def test_request_shape_on_the_real_openai_sdk():
    server = FakeServer(completion("Looking.", [("trace", {"key": "JOB-2003"})]))
    conv = KIConnectProvider(None, "dep", client=server.client()).start("SYS", ALL_TOOLS, "Q?")
    r = conv.generate()
    assert r.text == "Looking." and r.tool_calls[0].name == "trace"
    assert r.tool_calls[0].args == {"key": "JOB-2003"} and (r.input_tokens, r.output_tokens) == (50, 10)
    method, path, headers, body = server.requests[0]
    assert (method, path) == ("POST", "/api/v1/chat/completions")
    assert headers["authorization"] == "Bearer kic-test"
    assert body["model"] == "dep" and body["tool_choice"] == "auto"
    assert "max_completion_tokens" not in body and "max_tokens" not in body
    assert {t["function"]["name"] for t in body["tools"]} == {t.name for t in ALL_TOOLS}


def test_quota_429_waits_then_404_names_the_key_and_model():
    waits = []
    server = FakeServer(error(429, "quota_exceeded", "The usage limit has been exceeded.",
                              {"retry-after": "3"}), completion("ok"))
    c = KIConnectProvider(None, "dep", client=server.client(), sleep=waits.append).start("S", ALL_TOOLS, "Q")
    assert c.generate().text == "ok" and waits == [3.0]
    server2 = FakeServer(error(404, "model_not_found", "The requested deployment was not found."))
    c2 = KIConnectProvider(None, "nope", client=server2.client(), sleep=lambda s: None).start("S", ALL_TOOLS, "Q")
    with pytest.raises(ProviderError, match="KI:connect rejected.*KICONNECT_API_KEY.*'nope'.*deployment was not found"):
        c2.generate()


def test_forced_tool_choice_refused_falls_back_to_auto():
    server = FakeServer(error(400, "invalid_request_error", "tool_choice is not supported by this model"),
                        completion(calls=[("submit_answer", {"summary": "x"})]))
    c = KIConnectProvider(None, "dep", client=server.client(), sleep=lambda s: None).start("S", ALL_TOOLS, "Q")
    r = c.generate(force_tool="submit_answer")
    assert r.tool_calls[0].name == "submit_answer"
    assert server.requests[0][3]["tool_choice"]["function"]["name"] == "submit_answer"
    assert server.requests[1][3]["tool_choice"] == "auto"


def test_list_models():
    server = FakeServer((200, {"object": "list", "data": [
        {"id": "gpt-4o", "object": "model", "created": 0, "owned_by": "uni.example"},
        {"id": "llama-3.3-70b", "object": "model", "created": 0, "owned_by": "uni.example"}]}, {}))
    p = KIConnectProvider(None, None, client=server.client(), require_model=False)
    assert p.list_models() == ["gpt-4o", "llama-3.3-70b"]
    assert server.requests[0][:2] == ("GET", "/api/v1/models")


def test_whole_question_through_kiconnect():
    con = build()
    server = FakeServer(
        completion(calls=[("trace", {"key": "JOB-2003"})]),
        completion(calls=[("submit_answer", good_submission())]),
    )
    provider = KIConnectProvider(None, "dep", client=server.client())
    events = list(LogTracerAgent(provider, LogStore(con.cursor()), Settings(_env_file=None))
                  .run("Why did JOB-2003 fail?"))
    answer = next(e["data"] for e in events if e["event"] == "answer")
    assert [(e["file"].split("/")[-1], e["line"]) for e in answer["evidence"]] == [
        ("creative_2026-11-24.csv", 31), ("creative_2026-11-24.txt", 29),
        ("creative_2026-11-24.jsonl", 30)]
    done = next(e["data"] for e in events if e["event"] == "done")
    assert done["provider"] == "kiconnect" and done["llm_calls"] == 2
    # the tool result went back as a `tool` message tied to the call id
    second = server.requests[1][3]["messages"]
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "call_0"
    assert con.execute("SELECT count(*) FROM llm_calls").fetchone()[0] == 2
