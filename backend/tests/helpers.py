from __future__ import annotations

from typing import Any

from logtracer.assistant.providers.base import Conversation, LLMProvider, LLMResponse, ToolCall


class ScriptedProvider(LLMProvider):
    """Returns pre-written responses; records what the agent sends. No network."""

    name, model = "fake", "gemini-2.5-flash"

    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.forced: list[str | None] = []
        self.tool_results: list[list[tuple[ToolCall, dict[str, Any]]]] = []
        self.user_texts: list[str] = []

    def start(self, system, tools, user_message):
        self.tools, self.system, self.first_message = tools, system, user_message
        return _Conv(self)


class _Conv(Conversation):
    def __init__(self, p: ScriptedProvider):
        self.p = p

    def generate(self, force_tool=None):
        self.p.forced.append(force_tool)
        return self.p.responses.pop(0) if len(self.p.responses) > 1 else self.p.responses[0]

    def add_tool_results(self, results):
        self.p.tool_results.append(results)

    def add_user_text(self, text):
        self.p.user_texts.append(text)


def call(name: str, **args) -> ToolCall:
    return ToolCall(name=name, args=args, id=f"id-{name}")


def resp(*calls: ToolCall, text: str = "", tin: int = 100, tout: int = 20) -> LLMResponse:
    return LLMResponse(text=text, tool_calls=list(calls), input_tokens=tin, output_tokens=tout)


def good_submission(**over) -> dict[str, Any]:
    base = {
        "summary": "Publish of JOB-2003 failed because FMS rejected the JT upload (missing write permission).",
        "causal_chain": [
            {"step": 2, "server": "mait_linux1_teamcenter_app", "event_ids": [1002], "text": "FMS upload rejected"},
            {"step": 1, "server": "mait_win03_cad_converter", "event_ids": [1001], "text": "Conversion succeeded"},
            {"step": 3, "server": "mait_linux1_teamcenter_app", "event_ids": [1003], "text": "Publish failed"},
        ],
        "affected_systems": ["mait_win03_cad_converter", "mait_linux1_teamcenter_app"],
        "evidence_event_ids": [1001, 1002, 1003],
        "confidence": 0.85,
        "uncertainty": "No log shows why the permission is missing.",
        "counter_evidence": ["Converter reported SUCCESS."],
        "verification_steps": ["Check the FMS volume access policy."],
        "recommendation": "Grant write permission and resubmit.",
    }
    base.update(over)
    return base
