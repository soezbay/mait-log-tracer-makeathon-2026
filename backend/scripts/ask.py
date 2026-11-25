"""Ask the assistant a question from the command line (real LLM call, real database).

    python scripts/ask.py "Why did the publish of JOB-2003 fail on 24 Nov?"
    python scripts/ask.py --provider claude "..."          # needs ANTHROPIC_API_KEY
    python scripts/ask.py --provider groq --model qwen/qwen3.8-27b "..."   # needs GROQ_API_KEY
    python scripts/ask.py --list-models                                  # KI:connect deployments
    python scripts/ask.py --provider kiconnect --model <deployment> "..."  # needs KICONNECT_API_KEY
    python scripts/ask.py --db ../data/standin.duckdb --json "..."
Run it from the backend/ folder (it reads backend/.env).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb

from logtracer.assistant.agent import LogTracerAgent
from logtracer.assistant.config import Settings
from logtracer.assistant.data_access import LogStore
from logtracer.assistant.providers import ProviderError, create_provider


def _cost(eur: float | None) -> str:
    if eur is None:
        return "cost unknown (set PRICE_INPUT_PER_MTOK / PRICE_OUTPUT_PER_MTOK in .env)"
    return f"est. paid-tier cost {eur} EUR"


def _list_models(args) -> int:
    from logtracer.assistant.providers.kiconnect import KIConnectProvider

    settings = Settings()
    try:
        provider = KIConnectProvider(settings.kiconnect_api_key, None,
                                     base_url=(settings.kiconnect_base_url or "").strip() or None,
                                     require_model=False)
        for name in provider.list_models():
            print(name)
    except ProviderError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?")
    ap.add_argument("--db")
    ap.add_argument("--provider", choices=["gemini", "groq", "kiconnect", "claude"])
    ap.add_argument("--list-models", action="store_true",
                    help="KI:connect: list the deployment names your key may use, then exit")
    ap.add_argument("--model")
    ap.add_argument("--json", action="store_true", help="print the raw answer JSON only")
    ap.add_argument("--no-persist", action="store_true", help="do not store messages/hypotheses")
    args = ap.parse_args()

    if args.list_models:
        return _list_models(args)
    if not args.question:
        ap.error("a question is required (or use --list-models)")
    overrides = {k: v for k, v in {"db_path": args.db, "llm_provider": args.provider, "llm_model": args.model}.items() if v}
    settings = Settings(**overrides)
    if not Path(settings.db_path).exists():
        print(f"Database not found: {settings.db_path}. Build one with scripts/make_standin_db.py or set DB_PATH.", file=sys.stderr)
        return 1
    try:
        provider = create_provider(settings)
    except ProviderError as exc:
        print(exc, file=sys.stderr)
        return 1

    con = duckdb.connect(str(settings.db_path))
    agent = LogTracerAgent(provider, LogStore(con.cursor()), settings)
    answer = None
    for ev in agent.run(args.question, persist=not args.no_persist):
        kind, data = ev["event"], ev["data"]
        if kind == "step" and data["status"] == "done" and not args.json:
            print(f"  · {data['message']}  → {data['result']}", file=sys.stderr)
        elif kind == "answer":
            answer = data
        elif kind == "done" and not args.json:
            print(f"\n[{data['provider']}/{data['model']}] {data['llm_calls']} LLM calls, {data['tool_calls']} tool calls, "
                  f"{data['input_tokens']}+{data['output_tokens']} tokens, {_cost(data['cost_eur'])}, "
                  f"{data['duration_ms'] / 1000:.1f}s", file=sys.stderr)
        elif kind == "error":
            print(f"ERROR: {data['message']}", file=sys.stderr)
            return 2
    if answer is None:
        return 2
    if args.json:
        print(json.dumps(answer, indent=2, ensure_ascii=False))
        return 0
    print(f"\n{answer['reply']}\n")
    print(f"Hypothesis: {answer['summary']}  (confidence {answer['confidence']:.2f})\n")
    for s in answer["causal_chain"]:
        print(f"  {s['step']}. [{s['server']}] {s['text']}  (events {s['event_ids']})")
    print("\nEvidence:")
    for e in answer["evidence"]:
        print(f"  #{e['event_id']}  {e['server']} · {e['file']}:{e['line']} · {e['ts']}")
    print(f"\nUncertainty: {answer['uncertainty']}")
    for label, key in (("Counter-evidence", "counter_evidence"), ("Verify", "verification_steps")):
        if answer[key]:
            print(f"{label}:")
            for item in answer[key]:
                print(f"  - {item}")
    if answer["recommendation"]:
        print(f"\nRecommendation: {answer['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
