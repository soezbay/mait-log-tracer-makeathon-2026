from __future__ import annotations

import pytest
from fixtures import F_CSV, build
from helpers import ScriptedProvider, call, good_submission, resp

from logtracer.assistant.agent import LogTracerAgent
from logtracer.assistant.answer import SUBMIT_ANSWER_PARAMETERS, AnswerSubmission
from logtracer.assistant.config import Settings
from logtracer.assistant.data_access import LogStore
from logtracer.assistant.tools import TOOL_SPECS, ToolBox, collect_event_ids


@pytest.fixture
def con():
    return build()


@pytest.fixture
def box(con):
    return ToolBox(LogStore(con))


def settings(**kw):
    return Settings(_env_file=None, **kw)


# ----------------------------------------------------------------- tools
def test_search_events_by_job_and_seen_ids(box):
    r = box.execute("search_events", {"job_id": "job-2003"})
    assert [e["id"] for e in r["rows"]] == [1001, 1002, 1003]
    assert r["rows"][0]["ts"] == "2026-11-24T08:30:00Z"
    assert box.seen_event_ids == {1001, 1002, 1003}


def test_search_events_filters_level_server_text(box):
    r = box.execute("search_events", {"level": "ERROR", "server": "teamcenter", "text": "retry", "time_from": "2026-11-24"})
    assert [e["id"] for e in r["rows"]] == [1004]
    assert box.execute("search_events", {"time_to": "2026-11-23"})["total_matches"] == 0


def test_trace_warns_about_same_job_number(box):
    r = box.execute("trace", {"key": "JOB-2010"})
    assert len(r["time_clusters"]) == 2 and "warning" in r
    r2 = box.execute("trace", {"key": "JOB-2003"})
    assert len(r2["time_clusters"]) == 1 and r2["time_clusters"][0]["hosts"]


def test_error_groups_and_correlate(box):
    r = box.execute("get_error_groups", {"status": "failed"})
    assert r["rows"][0]["sample_event_ids"] == [1002, 1003]
    assert {1002, 1003} <= box.seen_event_ids
    c = box.execute("correlate", {"group_id": 2})
    assert c["linked_groups"][0]["other_group_id"] == 1 and c["linked_groups"][0]["status"] == "recovered"
    assert "error" in box.execute("correlate", {"group_id": 99})


def test_context_cross_server_window(box):
    r = box.execute("get_context", {"event_id": 1001, "window_seconds": 60})
    assert [e["id"] for e in r["other_servers_warn_error_in_window"]] == [1004, 1002, 1003]
    assert "error" in box.execute("get_context", {"event_id": 424242})


def test_stats_incidents_anomalies(box):
    s = box.execute("get_stats", {"time_from": "2026-11-24"})
    assert s["by_host"][0]["errors"] >= 1
    assert box.execute("get_incidents", {})["returned"] == 1
    assert box.execute("get_anomalies", {"server": "linux1"})["returned"] == 1


def test_tool_errors_are_returned_not_raised(con, box):
    assert "error" in box.execute("search_events", {"time_from": "yesterday"})
    assert "error" in box.execute("nope", {})
    assert "error" in box.execute("search_events", {"bogus": 1})
    con.execute("DROP TABLE group_members")
    con.execute("DROP TABLE error_groups")
    r = box.execute("get_error_groups", {})
    assert "not available" in r["error"]


def test_result_is_size_limited(con, box):
    con.execute(
        "INSERT INTO events (id, source_id, line_start, line_end, ts_utc, ingest_seq, host, level, "
        "message, raw) SELECT 5000+i, 4, i, i, TIMESTAMP '2026-11-25 00:00:00', 5000+i, 'h', 'INFO', "
        "repeat('x', 2000), 'x' FROM range(60) t(i)"
    )
    r = box.execute("search_events", {"time_from": "2026-11-25", "limit": 50})
    assert r["truncated"] and r["returned"] < 50


def test_collect_event_ids():
    assert collect_event_ids({"rows": [{"id": 1}, {"group_id": 5, "sample_event_ids": [7, 8]}]}) == {1, 7, 8}


def test_submit_schema_matches_pydantic_model():
    assert set(SUBMIT_ANSWER_PARAMETERS["properties"]) == set(AnswerSubmission.model_fields)
    assert set(SUBMIT_ANSWER_PARAMETERS["required"]) == set(AnswerSubmission.model_fields)
    assert len({t.name for t in TOOL_SPECS}) == len(TOOL_SPECS)


# ----------------------------------------------------------------- agent
def run(con, provider, question="Why did publish JOB-2003 fail?", **cfg):
    agent = LogTracerAgent(provider, LogStore(con), settings(**cfg))
    return list(agent.run(question, conversation_id="c1"))


def kinds(events):
    return [e["event"] for e in events]


def test_happy_path_builds_evidence_from_db(con):
    p = ScriptedProvider([
        resp(call("get_incidents"), call("trace", key="JOB-2003"), text="Looking."),
        resp(call("submit_answer", **good_submission())),
    ])
    ev = run(con, p)
    assert kinds(ev) == ["token", "step", "step", "step", "step", "answer", "done"]
    ans = next(e["data"] for e in ev if e["event"] == "answer")
    assert [s["step"] for s in ans["causal_chain"]] == [1, 2, 3]  # sorted
    first = ans["evidence"][0]
    assert (first["event_id"], first["file"], first["line"], first["ts"]) == (1001, F_CSV, 31, "2026-11-24T08:30:00Z")
    assert first["server"] == "mait_win03_cad_converter"
    done = next(e["data"] for e in ev if e["event"] == "done")
    assert done["llm_calls"] == 2 and done["input_tokens"] == 200 and done["tool_calls"] == 2
    assert done["cost_eur"] == pytest.approx((200 * 0.30 + 40 * 2.50) / 1e6 * 0.86)
    assert con.execute("SELECT count(*), sum(input_tokens) FROM llm_calls").fetchone() == (2, 200)
    assert con.execute("SELECT count(*) FROM hypotheses").fetchone()[0] == 1
    assert con.execute("SELECT role FROM chat_messages ORDER BY message_id").fetchall() == [("user",), ("assistant",)]


def test_hallucinated_ids_are_rejected_then_fixed(con):
    bad = good_submission(evidence_event_ids=[1001, 9999], causal_chain=[])
    p = ScriptedProvider([
        resp(call("trace", key="JOB-2003")),
        resp(call("submit_answer", **bad)),
        resp(call("submit_answer", **good_submission())),
    ])
    ev = run(con, p)
    assert kinds(ev)[-2:] == ["answer", "done"]
    err = p.tool_results[1][0][1]
    assert err["ids_not_in_database"] == [9999]


def test_ids_never_shown_to_the_model_are_rejected(con):
    p = ScriptedProvider([
        resp(call("search_events", job_id="JOB-2003")),
        resp(call("submit_answer", **good_submission(evidence_event_ids=[1001, 1004], causal_chain=[]))),
        resp(call("submit_answer", **good_submission())),
    ])
    run(con, p)
    assert p.tool_results[1][0][1]["ids_never_returned_by_a_tool"] == [1004]


def test_repeated_bad_submissions_degrade_to_verified_evidence(con):
    bad = good_submission(evidence_event_ids=[1001, 9999], confidence=0.9)
    p = ScriptedProvider([resp(call("trace", key="JOB-2003")), resp(call("submit_answer", **bad))])
    ev = run(con, p)
    ans = next(e["data"] for e in ev if e["event"] == "answer")
    assert ans["confidence"] <= 0.3 and "removed" in ans["uncertainty"]
    assert {e["event_id"] for e in ans["evidence"]} == {1001, 1002, 1003}
    assert 9999 not in {e["event_id"] for e in ans["evidence"]}


def test_no_evidence_needs_low_confidence(con):
    none = good_submission(evidence_event_ids=[], causal_chain=[], confidence=0.9)
    p = ScriptedProvider([resp(call("submit_answer", **none)), resp(call("submit_answer", **{**none, "confidence": 0.1}))])
    ev = run(con, p)
    assert "error" in p.tool_results[0][0][1]
    ans = next(e["data"] for e in ev if e["event"] == "answer")
    assert ans["evidence"] == [] and ans["confidence"] == 0.1


def test_percent_confidence_and_schema_problems(con):
    assert AnswerSubmission(**good_submission(confidence=85)).confidence == 0.85
    broken = good_submission()
    del broken["uncertainty"]
    p = ScriptedProvider([resp(call("trace", key="JOB-2003")), resp(call("submit_answer", **broken)), resp(call("submit_answer", **good_submission()))])
    run(con, p)
    assert "problems" in p.tool_results[1][0][1]


def test_submit_mixed_with_other_tools_is_deferred(con):
    p = ScriptedProvider([
        resp(call("trace", key="JOB-2003"), call("submit_answer", **good_submission())),
        resp(call("submit_answer", **good_submission())),
    ])
    ev = run(con, p)
    assert kinds(ev)[-2:] == ["answer", "done"]
    assert "on its own" in p.tool_results[0][1][1]["error"]


def test_round_limit_forces_submit_and_text_only_is_nudged(con):
    p = ScriptedProvider([
        resp(text="thinking"),
        resp(call("search_events", level="ERROR")),
        resp(call("search_events", level="ERROR")),
        resp(call("submit_answer", **good_submission(causal_chain=[], evidence_event_ids=[1002]))),
    ])
    ev = run(con, p, max_rounds=4)
    assert p.forced == [None, None, None, "submit_answer"]
    assert p.user_texts and kinds(ev)[-2:] == ["answer", "done"]


def test_tool_call_cap_forces_submit(con):
    p = ScriptedProvider([resp(call("search_events", level="ERROR")), resp(call("submit_answer", **good_submission(causal_chain=[], evidence_event_ids=[1002])))])
    run(con, p, max_tool_calls=1)
    assert p.forced == [None, "submit_answer"]


def test_no_answer_within_limit_is_an_error_event(con):
    p = ScriptedProvider([resp(call("search_events", level="ERROR"))])
    ev = run(con, p, max_rounds=2)
    assert kinds(ev)[-1] == "error"


def test_provider_error_becomes_error_event(con):
    from logtracer.assistant.providers.base import ProviderError

    class Boom(ScriptedProvider):
        def start(self, *a, **k):
            raise ProviderError("Gemini rate limit reached (free tier).")

    ev = run(con, Boom([resp()]))
    assert kinds(ev) == ["error"] and "rate limit" in ev[0]["data"]["message"]


def test_ask_collects_result_and_history_goes_into_prompt(con):
    p = ScriptedProvider([resp(call("trace", key="JOB-2003")), resp(call("submit_answer", **good_submission()))])
    agent = LogTracerAgent(p, LogStore(con), settings())
    result = agent.ask("And the converter?", history=[("Why did publish fail?", "FMS rejected the upload")], persist=False)
    assert result.answer and result.usage["llm_calls"] == 2 and len(result.steps) == 2
    assert "FMS rejected the upload" in p.first_message
    assert con.execute("SELECT count(*) FROM hypotheses").fetchone()[0] == 0
