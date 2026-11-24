from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fixtures import build
from google.genai import types
from helpers import ScriptedProvider, call, good_submission, resp

from logtracer.api import chat as chat_api
from logtracer.assistant.agent import SUBMIT_SPEC
from logtracer.assistant.providers.base import ProviderError, ToolCall, with_retries
from logtracer.assistant.providers.claude import ClaudeProvider
from logtracer.assistant.providers.gemini import GeminiProvider, _gemini_schema
from logtracer.assistant.tools import TOOL_SPECS

ALL_TOOLS = [*TOOL_SPECS, SUBMIT_SPEC]


# ----------------------------------------------------------------- Gemini
class _Code(Exception):
    def __init__(self, code):
        self.code = code


def gemini_response(parts, tin=10, tout=5, thoughts=3):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=tin, candidates_token_count=tout, thoughts_token_count=thoughts
        ),
    )


class FakeGemini:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append((model, list(contents), config))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_all_tool_schemas_are_valid_gemini_declarations():
    for t in ALL_TOOLS:
        types.FunctionDeclaration(name=t.name, description=t.description, parameters=_gemini_schema(t.parameters))
    schema = _gemini_schema(SUBMIT_SPEC.parameters)
    assert schema["type"] == "OBJECT" and schema["properties"]["causal_chain"]["items"]["properties"]["step"]["type"] == "INTEGER"


def test_gemini_roundtrip_with_tool_call_and_results():
    fc = types.Part(function_call=types.FunctionCall(name="trace", args={"key": "JOB-2003"}))
    client = FakeGemini(gemini_response([types.Part(text="Let me check."), fc]), gemini_response([types.Part(text="ok")]))
    conv = GeminiProvider(None, "gemini-2.5-flash", client=client).start("SYS", ALL_TOOLS, "Question?")
    r = conv.generate()
    assert r.text == "Let me check." and r.tool_calls == [ToolCall("trace", {"key": "JOB-2003"}, None)]
    assert (r.input_tokens, r.output_tokens) == (10, 8)  # thinking tokens count as output
    model, _contents, config = client.calls[0]
    assert model == "gemini-2.5-flash" and config.system_instruction == "SYS"
    assert {d.name for d in config.tools[0].function_declarations} == {t.name for t in ALL_TOOLS}
    assert config.automatic_function_calling.disable is True and config.tool_config is None

    conv.add_tool_results([(r.tool_calls[0], {"rows": [], "total_matches": 0})])
    last = conv.contents[-1]
    assert last.role == "user" and last.parts[0].function_response.name == "trace"
    assert conv.contents[-2].role == "model"  # raw model turn kept (thought signatures)
    conv.generate(force_tool="submit_answer")
    fcc = client.calls[1][2].tool_config.function_calling_config
    assert fcc.mode == "ANY" and fcc.allowed_function_names == ["submit_answer"]


def test_gemini_empty_candidate_keeps_history_valid_and_nudge_merges():
    empty = types.GenerateContentResponse(candidates=[types.Candidate(content=None)])
    conv = GeminiProvider(None, "m", client=FakeGemini(empty)).start("S", ALL_TOOLS, "Q")
    r = conv.generate()
    assert r.text == "" and r.tool_calls == [] and len(conv.contents) == 1
    conv.add_user_text("please continue")
    assert len(conv.contents) == 1 and len(conv.contents[0].parts) == 2


def test_gemini_retries_429_then_gives_readable_error():
    sleeps = []
    ok = gemini_response([types.Part(text="done")])
    c = GeminiProvider(None, "m", client=FakeGemini(_Code(429), _Code(503), ok), sleep=sleeps.append).start("S", ALL_TOOLS, "Q")
    assert c.generate().text == "done" and sleeps == [2.0, 4.0]
    c2 = GeminiProvider(None, "m", client=FakeGemini(*[_Code(429)] * 4), sleep=lambda s: None).start("S", ALL_TOOLS, "Q")
    with pytest.raises(ProviderError, match="rate limit"):
        c2.generate()
    c3 = GeminiProvider(None, "m", client=FakeGemini(_Code(403)), sleep=lambda s: None).start("S", ALL_TOOLS, "Q")
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        c3.generate()


def test_missing_keys_give_clear_errors():
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        GeminiProvider(None, "m")
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        ClaudeProvider(None, "m")


def test_with_retries_does_not_retry_other_errors():
    n = []
    with pytest.raises(KeyError):
        with_retries(lambda: n.append(1) or (_ for _ in ()).throw(KeyError()), lambda e: False, sleep=lambda s: None)
    assert len(n) == 1


# ----------------------------------------------------------------- Claude
class FakeAnthropic:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


def test_claude_roundtrip():
    r1 = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Checking"), SimpleNamespace(type="tool_use", id="tu1", name="trace", input={"key": "JOB-2003"})],
        usage=SimpleNamespace(input_tokens=50, output_tokens=12),
    )
    r2 = SimpleNamespace(content=[SimpleNamespace(type="text", text="done")], usage=SimpleNamespace(input_tokens=60, output_tokens=5))
    client = FakeAnthropic(r1, r2)
    conv = ClaudeProvider(None, "claude-sonnet-5-5", client=client).start("SYS", ALL_TOOLS, "Q?")
    r = conv.generate()
    assert r.tool_calls == [ToolCall("trace", {"key": "JOB-2003"}, "tu1")] and (r.input_tokens, r.output_tokens) == (50, 12)
    kw = client.calls[0]
    assert kw["system"] == "SYS" and kw["model"] == "claude-sonnet-5-5" and "tool_choice" not in kw
    assert {t["name"] for t in kw["tools"]} == {t.name for t in ALL_TOOLS} and "input_schema" in kw["tools"][0]
    conv.add_tool_results([(r.tool_calls[0], {"rows": []})])
    msg = conv.messages[-1]
    assert msg["role"] == "user" and msg["content"][0]["tool_use_id"] == "tu1"
    conv.add_user_text("continue")
    assert msg["content"][-1] == {"type": "text", "text": "continue"}
    conv.generate(force_tool="submit_answer")
    assert client.calls[1]["tool_choice"] == {"type": "tool", "name": "submit_answer"}


def test_claude_error_mapping():
    class E(Exception):
        status_code = 401

    c = ClaudeProvider(None, "m", client=FakeAnthropic(), sleep=lambda s: None)
    c.client.create = lambda **kw: (_ for _ in ()).throw(E())
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        c.start("S", ALL_TOOLS, "Q").generate()


# ----------------------------------------------------------------- API (SSE)
def parse_sse(text: str):
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(l.split(": ", 1) for l in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.fixture
def client():
    con = build()
    provider = ScriptedProvider([resp(call("trace", key="JOB-2003")), resp(call("submit_answer", **good_submission()))])
    chat_api.configure(cursor_factory=con.cursor, provider_factory=lambda: provider)
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api")
    yield TestClient(app), con, provider
    chat_api.configure()


def test_chat_streams_step_answer_done_and_stores_history(client):
    c, _con, _ = client
    r = c.post("/api/chat", json={"question": "Why did publish JOB-2003 fail?", "conversation_id": "conv-1"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    assert [e for e, _ in events] == ["step", "step", "answer", "done"]
    answer = events[2][1]
    assert answer["evidence"][0]["file"].endswith("creative_2026-11-24.csv")
    assert events[3][1]["conversation_id"] == "conv-1"
    h = c.get("/api/chat/conv-1").json()
    assert [m["role"] for m in h["messages"]] == ["user", "assistant"]


def test_chat_follow_up_uses_history(client):
    c, _con, provider = client
    c.post("/api/chat", json={"question": "Why did publish JOB-2003 fail?", "conversation_id": "conv-2"})
    provider.responses = [resp(call("submit_answer", **good_submission(causal_chain=[], evidence_event_ids=[])), tin=1) ]
    provider.responses[0].tool_calls[0].args["confidence"] = 0.1
    c.post("/api/chat", json={"question": "and the converter?", "conversation_id": "conv-2"})
    assert "Publish of JOB-2003 failed" in provider.first_message


def test_chat_validation_and_provider_errors():
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api")
    c = TestClient(app)
    assert c.post("/api/chat", json={"question": "x"}).status_code == 422

    def broken():
        raise ProviderError("GEMINI_API_KEY is not set (put it in backend/.env).")

    chat_api.configure(cursor_factory=build().cursor, provider_factory=broken)
    try:
        events = parse_sse(c.post("/api/chat", json={"question": "What is wrong today?"}).text)
    finally:
        chat_api.configure()
    assert events == [("error", {"message": "GEMINI_API_KEY is not set (put it in backend/.env)."})]
