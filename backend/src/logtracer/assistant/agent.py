"""The tool-use loop: question -> LLM -> tool calls -> results -> ... -> validated structured answer."""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .answer import SUBMIT_ANSWER_PARAMETERS, SUBMIT_TOOL_NAME, Answer, AnswerSubmission, Evidence
from .config import Settings, get_settings
from .costs import UsageTotals
from .data_access import LogStore
from .prompt import SYSTEM_PROMPT, build_user_message
from .providers.base import LLMProvider, ProviderError, ToolCall, ToolSpec
from .tools import TOOL_SPECS, ToolBox, step_label, summarize

log = logging.getLogger(__name__)

SUBMIT_SPEC = ToolSpec(
    name=SUBMIT_TOOL_NAME,
    description=(
        "Deliver the final answer once you have enough evidence, or have found that the logs cannot "
        "answer. Cite only event ids returned by tools."
    ),
    parameters=SUBMIT_ANSWER_PARAMETERS,
)

Event = dict[str, Any]  # {"event": "step" | "token" | "answer" | "done" | "error", "data": {...}}


@dataclass
class AgentResult:
    """Non-streaming result, handy for the evaluation script (P5)."""

    answer: dict[str, Any] | None
    usage: dict[str, Any]
    steps: list[dict[str, Any]]
    conversation_id: str
    error: str | None = None


class LogTracerAgent:
    def __init__(self, provider: LLMProvider, store: LogStore, settings: Settings | None = None):
        self.provider = provider
        self.store = store
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------ public
    def ask(self, question: str, **kw: Any) -> AgentResult:
        steps: list[dict[str, Any]] = []
        answer = usage = error = None
        conv_id = kw.get("conversation_id") or ""
        for ev in self.run(question, **kw):
            if ev["event"] == "step":
                steps.append(ev["data"])
            elif ev["event"] == "answer":
                answer = ev["data"]
            elif ev["event"] == "done":
                usage, conv_id = ev["data"], ev["data"].get("conversation_id", conv_id)
            elif ev["event"] == "error":
                error = ev["data"]["message"]
        return AgentResult(answer, usage or {}, steps, conv_id, error)

    def run(
        self,
        question: str,
        *,
        conversation_id: str | None = None,
        history: list[tuple[str, str]] | None = None,
        known_event_ids: set[int] | None = None,
        persist: bool = True,
    ) -> Iterator[Event]:
        conv_id = conversation_id or uuid.uuid4().hex[:12]
        started = time.monotonic()
        usage = UsageTotals(self.provider.name, self.provider.model)
        box = ToolBox(self.store)
        box.seen_event_ids |= known_event_ids or set()  # cited earlier in this conversation
        if persist:
            self.store.save_message(conv_id, "user", question)
        try:
            conv = self.provider.start(SYSTEM_PROMPT, [*TOOL_SPECS, SUBMIT_SPEC], build_user_message(question, history))
            yield from self._loop(conv, box, usage, conv_id, question, persist, started)
        except ProviderError as exc:
            yield {"event": "error", "data": {"message": str(exc), "conversation_id": conv_id}}
        except Exception as exc:
            log.exception("agent failed")
            yield {"event": "error", "data": {"message": f"Internal error: {type(exc).__name__}", "conversation_id": conv_id}}

    # ------------------------------------------------------------------ loop
    def _loop(self, conv, box: ToolBox, usage: UsageTotals, conv_id: str, question: str, persist: bool, started: float):
        cfg = self.settings
        tool_calls_made = submit_failures = nudges = 0
        last_error: dict[str, Any] | None = None

        for round_no in range(1, cfg.max_rounds + 1):
            force = (
                SUBMIT_TOOL_NAME
                if round_no == cfg.max_rounds or tool_calls_made >= cfg.max_tool_calls or nudges >= 2
                else None
            )
            t0 = time.monotonic()
            resp = conv.generate(force_tool=force)
            usage.add(conv_id, resp.input_tokens, resp.output_tokens, int((time.monotonic() - t0) * 1000), cfg, self.store)

            if resp.text:
                yield {"event": "token", "data": {"text": resp.text}}

            if not resp.tool_calls:
                nudges += 1
                conv.add_user_text(f"Continue with the tools if you need more evidence; otherwise call {SUBMIT_TOOL_NAME} now.")
                continue

            submit: ToolCall | None = None
            results: list[tuple[ToolCall, dict[str, Any]]] = []
            for call in resp.tool_calls:
                if call.name == SUBMIT_TOOL_NAME:
                    submit = call
                    continue
                tool_calls_made += 1
                label = step_label(call.name, call.args)
                yield {"event": "step", "data": {"round": round_no, "tool": call.name, "args": call.args,
                                                 "status": "running", "message": label}}
                result = box.execute(call.name, call.args)
                yield {"event": "step", "data": {"round": round_no, "tool": call.name, "args": call.args,
                                                 "status": "done", "message": label, "result": summarize(result)}}
                results.append((call, result))

            if submit is not None:
                if results:  # submitted together with other tool calls: it has not seen their results
                    results.append((submit, {"error": f"Call {SUBMIT_TOOL_NAME} on its own, after you have seen the tool results."}))
                else:
                    answer, error = self._finalize(submit.args, box)
                    if answer is None:
                        submit_failures += 1
                        last_error = error
                        if submit_failures > 2:
                            answer = self._degrade(submit.args, box)
                        else:
                            results.append((submit, error))
                    if answer is not None:
                        data = answer.model_dump(mode="json")
                        if persist:
                            self.store.save_message(conv_id, "assistant", answer.reply, data)
                            self.store.save_hypothesis(
                                conv_id, question, data, f"{self.provider.name}/{self.provider.model}"
                            )
                        yield {"event": "answer", "data": data}
                        yield {"event": "done", "data": {
                            "conversation_id": conv_id, "rounds": round_no, "tool_calls": tool_calls_made,
                            "duration_ms": int((time.monotonic() - started) * 1000), **usage.summary()}}
                        return
            conv.add_tool_results(results)

        yield {"event": "error", "data": {
            "message": "The assistant did not produce a valid answer within the round limit."
                       + (f" Last problem: {last_error}" if last_error else ""),
            "conversation_id": conv_id}}

    # ------------------------------------------------------------------ validation
    def _finalize(self, args: dict[str, Any], box: ToolBox) -> tuple[Answer | None, dict[str, Any]]:
        try:
            sub = AnswerSubmission.model_validate(args)
        except ValidationError as exc:
            problems = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:6]]
            return None, {"error": "The answer does not match the schema.", "problems": problems}

        cited = sub.cited_event_ids()
        existing = self.store.existing_event_ids(cited)
        missing = [i for i in cited if i not in existing]
        unseen = [i for i in cited if i in existing and i not in box.seen_event_ids]
        if missing or unseen:
            return None, {
                "error": "Some cited event ids are not valid evidence.",
                "ids_not_in_database": missing,
                "ids_never_returned_by_a_tool": unseen,
                "instruction": "Remove these ids from causal_chain and evidence_event_ids; do not "
                               "replace them with other guessed ids. Cite only `id` values tools "
                               "returned (for re-runs: the sample_event_ids). Keep the rest of the "
                               f"answer and call {SUBMIT_TOOL_NAME} again.",
            }
        if not [c for c in sub.counter_evidence if c.strip()]:
            return None, {
                "error": "counter_evidence is empty.",
                "instruction": "Add at least one item: a fact from the logs that argues against your "
                               "hypothesis or an alternative cause you ruled out (say how). If you found "
                               "none, say which checks found nothing. Then call "
                               f"{SUBMIT_TOOL_NAME} again with the same evidence.",
            }
        missed = _unmentioned_related(sub, box.related_failures)
        if missed:
            key, info = missed
            keys = info["keys"]
            span = f"{keys[0]} ... {keys[-1]}" if len(keys) > 1 else (keys[0] if keys else "")
            return None, {
                "error": "The answer ignores related jobs that also logged errors.",
                "facts": f"trace({key}) found {info['events']} log lines of {info['count']} other "
                         f"jobs/traces ({span}) that mention {key} with WARN/ERROR.",
                "instruction": "Say in summary or uncertainty whether they failed the same way (e.g. "
                               "re-runs) and how many there are. Keep the rest, also the form of reply the user wants, and call "
                               f"{SUBMIT_TOOL_NAME} again.",
            }
        uncited = _uncited_trace_failures(sub, box)
        if uncited:
            box.trace_failures.clear()  # ask once; a second answer is accepted as it is
            return None, {
                "error": "The answer leaves out WARN/ERROR lines that trace found for this job.",
                "uncited_lines": uncited,
                "instruction": "Put each line in the causal chain if it is part of the failure (cite "
                               "its id), or say in counter_evidence why it is not (e.g. harmless) and "
                               "cite its id in evidence_event_ids. Keep the rest and call "
                               f"{SUBMIT_TOOL_NAME} again.",
            }
        if not cited and sub.confidence > 0.2:
            return None, {
                "error": "No evidence cited.",
                "instruction": "Either find evidence with the tools, or set confidence to 0.2 or lower and "
                               "explain what the logs do not show.",
            }
        return self._build(sub, cited, box.seen_event_ids), {}

    def _build(self, sub: AnswerSubmission, ids: list[int], seen: set[int] | None = None) -> Answer:
        evidence = [Evidence(**row) for row in self.store.evidence_for(ids)]
        _replace_internal_ids(sub, self.store, seen or set())
        chain = sorted(sub.causal_chain, key=lambda s: s.step)
        return Answer(
            reply=sub.reply.strip() or sub.summary,
            summary=sub.summary,
            causal_chain=chain,
            affected_systems=sub.affected_systems,
            evidence=evidence,
            confidence=sub.confidence,
            uncertainty=sub.uncertainty,
            counter_evidence=sub.counter_evidence,
            verification_steps=sub.verification_steps,
            recommendation=sub.recommendation,
        )

    def _degrade(self, args: dict[str, Any], box: ToolBox) -> Answer:
        """After repeated invalid submissions: keep only verifiable evidence and say so."""
        try:
            sub = AnswerSubmission.model_validate(args)
        except ValidationError:
            sub = AnswerSubmission(summary=str(args.get("summary") or "No reliable answer."), confidence=0.0,
                                   uncertainty="The assistant could not produce a valid structured answer.")
        cited = sub.cited_event_ids()
        existing = self.store.existing_event_ids(cited)
        valid = [i for i in cited if i in existing and i in box.seen_event_ids]
        if len(valid) < len(cited):  # only then is the evidence weaker than the model claimed
            for step in sub.causal_chain:
                step.event_ids = [i for i in step.event_ids if i in valid]
            sub.evidence_event_ids = [i for i in sub.evidence_event_ids if i in valid]
            sub.confidence = min(sub.confidence, 0.3)
            sub.uncertainty += (" [Automatic check: some cited event ids could not be verified and "
                                "were removed.]")
        if not [c for c in sub.counter_evidence if c.strip()]:
            sub.counter_evidence = ["The assistant gave no counter-evidence; treat the hypothesis with care."]
        return self._build(sub, valid, box.seen_event_ids)


# Words that only count as a mention in the plural or as a phrase: "re-run the publish" is advice
# (seen live), not a statement about the 49 failed re-runs.
_RERUN_WORDS = ("re-runs", "reruns", "re runs", "other jobs", "other runs", "repeated", "recurr")


# "ID 786770", "event 30031", "event IDs 36746-36970", "INFO 34031": internal ids the user cannot
# look up. The prompt forbids them, but models still write them now and then.
_ID_MENTION = re.compile(
    r"\b(?:(?:event\s*)?ids?|events?|(?:debug|info|warn|warning|error|fatal)(?:\s+line)?)"
    r"\s*[:#]?\s*(\d{3,}(?:\s*(?:,|-|–|and|/)\s*\d{3,})*)\b",
    re.IGNORECASE,
)


def _replace_internal_ids(sub: AnswerSubmission, store: LogStore, seen: set[int]) -> None:
    """Write event ids in text fields as the file:line the evidence list shows."""
    texts = [sub.reply, sub.summary, sub.uncertainty, sub.recommendation, *sub.counter_evidence,
             *sub.verification_steps, *(step.text for step in sub.causal_chain)]
    found = {int(n) for t in texts for m in _ID_MENTION.finditer(t or "")
             for n in re.findall(r"\d{3,}", m.group(1))}
    ids = sorted(found & seen)
    if not ids:
        return
    refs = {r["event_id"]: f"{str(r['file'] or '').replace(chr(92), '/').split('/')[-1]}:{r['line']}"
            for r in store.evidence_for(ids)}

    def fix(text: str) -> str:
        def one(m: re.Match[str]) -> str:
            numbers = [int(n) for n in re.findall(r"\d{3,}", m.group(1))]
            if not numbers or any(n not in refs for n in numbers):
                return m.group(0)  # not (all) internal ids: leave the text alone
            word = m.group(0)[: m.start(1) - m.start(0)].rstrip(" :#")
            level = word.split()[0].upper() if word and word.split()[0].lower() in (
                "debug", "info", "warn", "warning", "error", "fatal") else ""
            label = f"{level} line" if level else ("lines" if len(numbers) > 1 else "line")
            before = m.string[: m.start()].rstrip()
            if not level and (not before or before[-1] in ".!?:"):  # starts a sentence
                label = label.capitalize()
            return f"{label} {', '.join(refs[n] for n in numbers)}"
        return _ID_MENTION.sub(one, text) if text else text

    sub.reply, sub.summary = fix(sub.reply), fix(sub.summary)
    sub.uncertainty, sub.recommendation = fix(sub.uncertainty), fix(sub.recommendation)
    sub.counter_evidence = [fix(t) for t in sub.counter_evidence]
    sub.verification_steps = [fix(t) for t in sub.verification_steps]
    for step in sub.causal_chain:
        step.text = fix(step.text)


def _uncited_trace_failures(sub: AnswerSubmission, box: ToolBox) -> list[dict[str, Any]]:
    """WARN/ERROR lines of a traced job that the answer neither cites nor explains away."""
    cited = set(sub.cited_event_ids())
    return [
        {k: line.get(k) for k in ("id", "host", "component", "level", "message")}
        for lines in box.trace_failures.values() for line in lines
        if line.get("id") not in cited
    ]


def _unmentioned_related(
    sub: AnswerSubmission, related: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]] | None:
    """The first traced key whose failing related jobs the answer does not mention at all."""
    text = " ".join([
        sub.reply, sub.summary, sub.uncertainty, sub.recommendation, *sub.counter_evidence,
        *sub.verification_steps, *(step.text for step in sub.causal_chain),
    ]).lower()
    for key, info in related.items():
        keys = [k.lower() for k in info.get("keys") or []]
        prefix = os.path.commonprefix(keys) if len(keys) > 1 else ""
        mentioned = (
            any(k in text for k in keys)
            or (len(prefix) > len(key) and prefix in text)
            or re.search(rf"\b{int(info.get('count') or 0)}\b", text) is not None
            or any(w in text for w in _RERUN_WORDS)
        )
        if not mentioned:
            return key, info
    return None
