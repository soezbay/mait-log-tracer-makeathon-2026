from __future__ import annotations

import json
from datetime import datetime

import pytest
from fixtures import F_CSV, TC, build
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
def ids(table):
    """Event ids of a compact table {"cols": [...], "rows": [[...]]}."""
    return [row[table["cols"].index("id")] for row in table["rows"]]


def col(table, name):
    return [row[table["cols"].index(name)] for row in table["rows"]]


def test_search_events_by_job_and_seen_ids(box):
    r = box.execute("search_events", {"job_id": "job-2003"})
    assert ids(r) == [1001, 1002, 1003]
    assert col(r, "ts")[0] == "2026-11-24T08:30:00Z"
    assert "trace_id" not in r["cols"]  # empty columns are left out
    assert box.seen_event_ids == {1001, 1002, 1003}


def test_text_search_reads_the_whole_log_line(box):
    # JOB-2003 is not in any message, only in the original line (job=JOB-2003)
    r = box.execute("search_events", {"text": "JOB-2003"})
    assert ids(r) == [1001, 1002, 1003]


def add_reruns(con, n_runs, start_id=5000):
    """Re-runs like JOB-2003-R01: same failure, different job id (as in the real log package)."""
    rows = []
    for k in range(1, n_runs + 1):
        job = f"JOB-2003-R{k:02d}"
        for j, (host, comp, msg) in enumerate([
            (TC, "fms/fsc", "Upload rejected; access policy lacks target volume write permission"),
            (TC, "teamcenter/workflow", "Publish task failed: no registered result"),
        ]):
            i = start_id + 2 * k + j
            rows.append((i, 4, i, i, datetime(2026, 11, 24, 8, 30, 8 + j), i, host, comp, "ERROR",
                         job, msg, f"2026-11-24T08:30:0{8 + j}Z ERROR job={job} {msg}"))
    con.executemany(
        "INSERT INTO events (id, source_id, line_start, line_end, ts_utc, ingest_seq, host, "
        "component, level, job_id, message, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def test_trace_reports_related_reruns_and_makes_them_citable(con, box):
    add_reruns(con, 7)
    r = box.execute("trace", {"key": "JOB-2003"})
    assert ids(r) == [1001, 1002, 1003]  # the job itself
    rel = r["related"]
    assert rel["events"] == 14 and rel["keys"]["count"] == 7
    assert rel["keys"]["first"][0] == "JOB-2003-R01" and rel["keys"]["last"][-1] == "JOB-2003-R07"
    assert sum(col(rel["groups"], "count")) == 14  # every related line is counted
    samples = [i for s in col(rel["groups"], "sample_event_ids") for i in s]
    assert samples and set(samples) <= box.seen_event_ids  # the model may cite them
    assert all(len(s) == 5 for s in col(rel["groups"], "sample_event_ids"))  # up to 5 per group


def test_few_reruns_each_get_a_sample_id(con, box):
    # 3 re-runs, 2 lines each: every re-run has a citable id, so none has to be guessed
    add_reruns(con, 3)
    rel = box.execute("trace", {"key": "JOB-2003"})["related"]
    assert sorted(i for s in col(rel["groups"], "sample_event_ids") for i in s) == list(range(5002, 5008))


def test_truncated_search_lists_different_lines_and_counts_all(con, box):
    add_reruns(con, 30)
    r = box.execute("search_events", {"text": "JOB-2003", "limit": 10})
    assert r["truncated"] and r["total_matches"] == 63
    patterns = list(zip(col(r, "host"), col(r, "component"), col(r, "message")))
    assert max(patterns.count(p) for p in patterns) <= 2  # no wall of repeats
    assert 1001 in ids(r) and 1002 in ids(r) and 1003 in ids(r)  # the rare lines survive
    assert sum(col(r["groups"], "count")) == 63  # nothing silently dropped


def test_search_events_filters_level_server_text(box):
    r = box.execute("search_events", {"level": "ERROR", "server": "teamcenter", "text": "retry", "time_from": "2026-11-24"})
    assert ids(r) == [1004]
    assert box.execute("search_events", {"time_to": "2026-11-23"})["total_matches"] == 0


def test_empty_time_window_says_where_the_matches_are(box):
    # A guessed date range must not hide logs: the result points to the matches outside it.
    r = box.execute("search_events", {"text": "retry", "level": "ERROR",
                                      "time_from": "2026-11-20", "time_to": "2026-11-22"})
    assert r["total_matches"] == 0
    hint = r["outside_time_range"]
    assert hint["total_matches"] >= 1 and hint["first"].startswith("2026-11-24")
    assert "without time_from/time_to" in r["note"]
    # no hint when the other filters match nothing either
    none = box.execute("search_events", {"text": "no such text", "time_from": "2026-11-20"})
    assert "outside_time_range" not in none and "note" not in none


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
    assert ids(r["other_servers_warn_error_in_window"]) == [1004, 1002, 1003]
    assert "error" in box.execute("get_context", {"event_id": 424242})


def test_stats_incidents_anomalies(box):
    s = box.execute("get_stats", {"time_from": "2026-11-24"})
    assert s["by_host"][0]["errors"] >= 1
    incidents = box.execute("get_incidents", {})
    assert incidents["returned"] == 1
    assert 1002 in box.seen_event_ids  # incidents come with events the model may cite
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


def test_uncited_trace_errors_are_sent_back_once(con):
    # The answer skips the FMS rejection (1002, ERROR) that trace found for the job.
    skip = good_submission(evidence_event_ids=[1001, 1003],
                           causal_chain=[good_submission()["causal_chain"][i] for i in (1, 2)])
    p = ScriptedProvider([
        resp(call("trace", key="JOB-2003")),
        resp(call("submit_answer", **skip)),
        resp(call("submit_answer", **skip)),  # asked once only: the second answer is accepted
    ])
    ev = run(con, p)
    err = p.tool_results[1][0][1]
    assert [line["id"] for line in err["uncited_lines"]] == [1002]
    ans = next(e["data"] for e in ev if e["event"] == "answer")
    assert ans["confidence"] == 0.85 and "removed" not in ans["uncertainty"]


def test_degrade_without_bad_ids_keeps_the_confidence(con):
    # Three answers without counter-evidence: degraded, but no id was wrong, so no 0.3 cap.
    weak = good_submission(counter_evidence=[])
    p = ScriptedProvider([resp(call("trace", key="JOB-2003"))]
                         + [resp(call("submit_answer", **weak))] * 3)
    ans = next(e["data"] for e in run(con, p) if e["event"] == "answer")
    assert ans["confidence"] == 0.85 and "removed" not in ans["uncertainty"]
    assert ans["counter_evidence"]


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


def test_default_gemini_model_has_a_price():
    from logtracer.assistant.config import DEFAULT_MODELS
    from logtracer.assistant.costs import estimate_cost_eur

    # 1M input + 1M output tokens at 0.75 + 3.75 USD, converted with the default 0.86 EUR/USD
    cost = estimate_cost_eur(DEFAULT_MODELS["gemini"], 1_000_000, 1_000_000)
    assert cost == pytest.approx((0.75 + 3.75) * 0.86)


def test_answer_without_counter_evidence_is_sent_back(con):
    bad = good_submission(counter_evidence=[])
    p = ScriptedProvider([
        resp(call("trace", key="JOB-2003")),
        resp(call("submit_answer", **bad)),
        resp(call("submit_answer", **good_submission())),
    ])
    ev = run(con, p)
    ans = next(e["data"] for e in ev if e["event"] == "answer")
    assert ans["counter_evidence"] == ["Converter reported SUCCESS."]
    assert "counter_evidence is empty" in json.dumps([r for _, r in p.tool_results[-1]])


def test_trace_puts_related_failures_first_as_a_sentence(con, box):
    add_reruns(con, 7)
    r = box.execute("trace", {"key": "JOB-2003"})
    assert list(r)[:2] == ["key", "related_summary"]
    sentence = r["related_summary"]
    assert "14 log lines of 7 OTHER jobs" in sentence and "JOB-2003-R01 ... JOB-2003-R07" in sentence
    assert "7x ERROR" in sentence
    assert box.related_failures["JOB-2003"]["count"] == 7


def test_answer_ignoring_failed_reruns_is_sent_back(con):
    add_reruns(con, 7)
    fixed = good_submission(
        summary="Publish of JOB-2003 failed: FMS rejected the upload. The same failure repeated in "
                "7 re-runs (JOB-2003-R01 ... R07).")
    p = ScriptedProvider([
        resp(call("trace", key="JOB-2003")),
        resp(call("submit_answer", **good_submission())),  # says nothing about the re-runs
        resp(call("submit_answer", **fixed)),
    ])
    ev = run(con, p)
    ans = next(e["data"] for e in ev if e["event"] == "answer")
    assert "re-runs" in ans["summary"]
    sent_back = json.dumps([r for _, r in p.tool_results[-1]])
    assert "ignores related jobs" in sent_back and "7 other jobs" in sent_back


@pytest.mark.parametrize("written", ["2003", "job 2003", "Job-2003", "JOB_2003", "Auftrag 2003", "job2003"])
def test_trace_understands_how_people_write_a_job(box, written):
    assert box.execute("trace", {"key": written})["key"].upper() == "JOB-2003"


def test_trace_keeps_numbers_that_are_no_job(box):
    assert box.execute("trace", {"key": "99999"})["key"] == "99999"


def test_reply_is_the_direct_answer_and_kept_in_the_history(con):
    reply = "Yes, all of them failed the same way."
    p = ScriptedProvider([resp(call("trace", key="JOB-2003")),
                          resp(call("submit_answer", **good_submission(reply=f" {reply} ")))])
    ev = run(con, p)
    ans = next(e["data"] for e in ev if e["event"] == "answer")
    assert list(ans)[:2] == ["reply", "summary"] and ans["reply"] == reply
    assert ans["summary"] != reply and len(ans["evidence"]) == 3  # the analysis is still there
    stored = con.execute("SELECT content FROM chat_messages WHERE role = 'assistant'").fetchall()
    assert stored == [(reply,)]


def test_follow_up_may_cite_earlier_evidence_without_a_tool_call(con):
    store = LogStore(con.cursor())
    first = ScriptedProvider([resp(call("trace", key="JOB-2003")),
                              resp(call("submit_answer", **good_submission(reply="FMS rejected it.")))])
    list(LogTracerAgent(first, store, settings()).run("Why?", conversation_id="c1"))
    # A question that got no answer must not shift the pairs.
    store.save_message("c1", "user", "stopped question")
    history, ids = store.follow_up_context("c1")
    assert [q for q, _ in history] == ["Why?"] and ids == {1001, 1002, 1003}
    assert "FMS rejected it." in history[0][1] and "Hypothesis: Publish of JOB-2003" in history[0][1]
    assert "Cited event ids: [1001, 1002, 1003]" in history[0][1]

    second = ScriptedProvider([resp(call("submit_answer", **good_submission(reply="Simply: no permission.")))])
    ev = list(LogTracerAgent(second, store, settings()).run(
        "Simpler please", conversation_id="c1", history=history, known_event_ids=ids))
    ans = next(e["data"] for e in ev if e["event"] == "answer")
    assert ans["reply"] == "Simply: no permission." and len(ans["evidence"]) == 3
    assert [q for q, _ in store.follow_up_context("c1")[0]] == ["Why?", "Simpler please"]
    # Without that conversation the same ids are still not accepted.
    other = ScriptedProvider([resp(call("submit_answer", **good_submission()))] * 3)
    ev = list(LogTracerAgent(other, store, settings()).run("Simpler please", conversation_id="c2"))
    ans = next(e["data"] for e in ev if e["event"] == "answer")
    assert ans["evidence"] == [] and ans["confidence"] <= 0.3


def test_follow_up_context_keeps_the_last_turns(con):
    store = LogStore(con.cursor())
    for i in range(5):
        store.save_message("c", "user", f"q{i}")
        store.save_message("c", "assistant", f"a{i}", {"summary": f"a{i}", "evidence": []})
    assert store.follow_up_context("c") == ([("q2", "a2"), ("q3", "a3"), ("q4", "a4")], set())
    assert store.follow_up_context("unknown") == ([], set())


def test_missing_reply_falls_back_to_the_summary(con):
    p = ScriptedProvider([resp(call("trace", key="JOB-2003")),
                          resp(call("submit_answer", **good_submission()))])
    ans = next(e["data"] for e in run(con, p) if e["event"] == "answer")
    assert ans["reply"] == ans["summary"]


def test_answer_naming_a_rerun_is_accepted_first_time(con):
    add_reruns(con, 3)
    ok = good_submission(uncertainty="JOB-2003-R02 failed the same way; logs do not show why.")
    p = ScriptedProvider([resp(call("trace", key="JOB-2003")), resp(call("submit_answer", **ok))])
    ev = run(con, p)
    assert any(e["event"] == "answer" for e in ev)
    assert len(p.tool_results) == 1  # no second submit was needed


def test_info_only_related_lines_do_not_force_a_mention(con, box):
    con.execute(
        "INSERT INTO events (id, source_id, line_start, line_end, ts_utc, ingest_seq, host, level, "
        "job_id, message, raw) VALUES (9001, 4, 1, 1, TIMESTAMP '2026-11-24 09:00:00', 9001, 'h', "
        "'INFO', 'AUDIT-7', 'audit entry', 'INFO job=AUDIT-7 parent=JOB-2003 audit entry')"
    )
    r = box.execute("trace", {"key": "JOB-2003"})
    assert r["related"]["events"] == 1  # still reported
    assert box.related_failures == {}  # but nothing failed, so no mention is required


def test_advice_to_rerun_is_not_a_mention_of_the_reruns(con):
    # Seen live (KI:connect, Mistral Small 4): the recommendation said "re-run the publish" and the
    # check took that as mentioning the 49 failed re-runs.
    add_reruns(con, 7)
    advice_only = good_submission(recommendation="Grant write permission, then re-run the publish.")
    p = ScriptedProvider([
        resp(call("trace", key="JOB-2003")),
        resp(call("submit_answer", **advice_only)),
        resp(call("submit_answer", **good_submission(
            uncertainty="The same failure hit all 7 re-runs; logs do not show why."))),
    ])
    ev = run(con, p)
    assert any(e["event"] == "answer" for e in ev)
    sent_back = json.dumps([r for _, r in p.tool_results[-1]])
    assert "ignores related jobs" in sent_back
