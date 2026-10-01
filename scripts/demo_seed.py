"""Generate deterministic fixture sessions without a running server.

Default: writes fixtures/generated_demo_sessions.json using real application
orchestration and offline provider doubles. Output faithfully includes defects.
--base-url instead populates a running app by replaying the three scenarios.
Live mode requires /health to report demo_mode=true and mock SMS/telephony;
weather may use current data. Server IDs/timestamps are then nondeterministic.
No SMS scenario is sent. Courier complaint is explicitly requested by the fixture.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from evals.sandbox import isolated_app, new_session, turn
from evals.trace import validate_trace


def normalize(value, sid: str, stable_id: str):
    if isinstance(value, dict):
        return {key: ("2026-10-01T09:00:00+05:30" if key in {"ts", "timestamp", "created_at", "updated_at"}
                      else normalize(item, sid, stable_id)) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item, sid, stable_id) for item in value]
    return value.replace(sid, stable_id) if isinstance(value, str) else value


def seed(client, deterministic: bool) -> dict:
    scenarios = json.loads((ROOT / "fixtures/demo_scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    sessions = []
    for scenario in scenarios:
        sid = new_session(client)
        responses = [turn(client, sid, text) for text in scenario["turns"]]
        details = client.get(f"/sessions/{sid}")
        details.raise_for_status()
        trace = client.get(f"/sessions/{sid}/events")
        trace.raise_for_status()
        item = {"scenario": scenario["id"], "expectations": scenario,
                "session": details.json(), "responses": responses,
                "events": trace.json()["events"],
                "trace_errors": validate_trace(trace.json()["events"])}
        sessions.append(normalize(item, sid, f"demo-{scenario['id']}") if deterministic else item)
    return {"demo": True, "mode": "offline replay" if deterministic else "server replay",
            "notice": "Observed application output; expectations are not assertions of success.", "sessions": sessions}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Optional already-running demo BoloAI server")
    parser.add_argument("--output", type=Path, default=ROOT / "fixtures/generated_demo_sessions.json")
    args = parser.parse_args()
    if args.base_url:
        import httpx
        with httpx.Client(base_url=args.base_url, timeout=30) as client:
            health = client.get("/health")
            health.raise_for_status()
            status = health.json()
            if status.get("demo_mode") is not True or status.get("providers", {}).get("exotel", {}).get("configured") is not False:
                parser.error("Live seeding requires demo_mode=true and Exotel unconfigured")
            report = seed(client, deterministic=False)
    else:
        with isolated_app() as client:
            report = seed(client, deterministic=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in report["sessions"]:
        print(f"{item['scenario']}: {item['session']['session_id']} ({len(item['trace_errors'])} trace issues)")
    print(f"Saved {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
