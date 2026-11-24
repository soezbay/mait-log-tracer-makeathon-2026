"""Interface 3: the assistant's answer format (owned by P3).

Two shapes:
* ``AnswerSubmission``: what the LLM sends through the ``submit_answer`` tool. It cites event IDs only.
* ``Answer``: what the API returns. The backend turns the cited IDs into evidence with file, line and
  time taken from the database, so the LLM can never invent a file or a line number.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

SUBMIT_TOOL_NAME = "submit_answer"


class CausalStep(BaseModel):
    step: int = Field(ge=1)
    server: str
    event_ids: list[int] = Field(default_factory=list)
    text: str


class AnswerSubmission(BaseModel):
    """Validated arguments of the ``submit_answer`` tool call."""

    summary: str = Field(min_length=1)
    causal_chain: list[CausalStep] = Field(default_factory=list)
    affected_systems: list[str] = Field(default_factory=list)
    evidence_event_ids: list[int] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: str = Field(min_length=1)
    counter_evidence: list[str] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    recommendation: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def _percent_to_fraction(cls, v: Any) -> Any:
        # Some models answer 85 instead of 0.85.
        if isinstance(v, (int, float)) and 1 < v <= 100:
            return v / 100
        return v

    def cited_event_ids(self) -> list[int]:
        ids: list[int] = []
        for step in self.causal_chain:
            ids.extend(step.event_ids)
        ids.extend(self.evidence_event_ids)
        return list(dict.fromkeys(ids))


class Evidence(BaseModel):
    event_id: int
    server: str | None = None
    file: str | None = None
    line: int | None = None
    ts: str | None = None  # ISO-8601 UTC


class Answer(BaseModel):
    summary: str
    causal_chain: list[CausalStep]
    affected_systems: list[str]
    evidence: list[Evidence]
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: str
    counter_evidence: list[str]
    verification_steps: list[str]
    recommendation: str


# Hand-written JSON schema for the tool (flat, no $ref: works with Gemini, Claude and Groq alike).
# Kept short: it is sent with every model call. The rules behind it are in the system prompt.
_IDS = {"type": "array", "items": {"type": "integer"}}
_TEXTS = {"type": "array", "items": {"type": "string"}}
SUBMIT_ANSWER_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "1-3 sentences: what failed and why"},
        "causal_chain": {
            "type": "array",
            "description": "cause -> effect steps across servers",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "integer"},
                    "server": {"type": "string"},
                    "event_ids": _IDS,
                    "text": {"type": "string"},
                },
                "required": ["step", "server", "event_ids", "text"],
            },
        },
        "affected_systems": _TEXTS,
        "evidence_event_ids": {**_IDS, "description": "every cited event id"},
        "confidence": {"type": "number", "description": "0.0 to 1.0"},
        "uncertainty": {"type": "string", "description": "what the logs do NOT show"},
        "counter_evidence": {**_TEXTS, "description": "at least 1 item"},
        "verification_steps": _TEXTS,
        "recommendation": {"type": "string"},
    },
    "required": [
        "summary",
        "causal_chain",
        "affected_systems",
        "evidence_event_ids",
        "confidence",
        "uncertainty",
        "counter_evidence",
        "verification_steps",
        "recommendation",
    ],
}
