"""One-command readiness report. Starts a temporary loopback mock server by default.

--mock-url http://127.0.0.1:9001 checks an existing mock instead.
Exit 0 = all checks pass; 1 = failures, xfails, skips or evaluation gaps;
2 = runner error. Live external providers are never used by smoke/eval tests.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import socket
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True


def probe_mock(url: str | None) -> dict:
    import httpx
    from fastapi.testclient import TestClient
    from mock_services.main import create_app
    with (httpx.Client(base_url=url, timeout=3) if url else TestClient(create_app())) as client:
        response = client.get("/health")
        response.raise_for_status()
        data = response.json()
        if data.get("service") != "boloai-mock-services" or data.get("demo") is not True or not data.get("ok"):
            raise ValueError("Endpoint is not a healthy BoloAI demo mock")
        return {"passed": True, "mode": url or "in-process ASGI (no listening server checked)"}


def check_mock_availability(url: str | None) -> dict:
    if url:
        return probe_mock(url)
    # OS selects an unused port; if the small bind/launch race occurs, fail visibly.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command = [sys.executable, "-B", "-m", "uvicorn", "mock_services.main:app",
               "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"]
    log_path = ROOT / "evals/latest_mock_server.txt"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    result = probe_mock(f"http://127.0.0.1:{port}")
                    result["mode"] = "temporary standalone loopback server"
                    return result
                except Exception:
                    time.sleep(0.15)
            raise RuntimeError(f"Temporary mock did not become available; see {log_path}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def summarize_xml(path: Path) -> dict:
    groups = {key: {"passed": 0, "failed": 0, "xfail": 0, "skipped": 0} for key in
              ("Core API", "Sessions", "Mock Courier", "Mock SMS", "Mock Schemes", "Agent Safety", "Event Traces", "Harness")}
    for case in ET.parse(path).getroot().iter("testcase"):
        identity = case.get("classname", "") + "." + case.get("name", "")
        if "test_agent_safety" in identity:
            group = "Agent Safety"
        elif "test_trace_validation" in identity:
            group = "Event Traces"
        elif "test_evaluation_harness" in identity:
            group = "Harness"
        elif "test_mock_services" in identity:
            group = "Mock SMS" if "sms" in identity else "Mock Courier" if "courier" in identity else "Mock Schemes"
        elif "session" in identity or "context" in identity:
            group = "Sessions"
        else:
            group = "Core API"
        skipped = case.find("skipped")
        status = "failed" if case.find("failure") is not None or case.find("error") is not None else (
            "xfail" if skipped is not None and skipped.get("type") == "pytest.xfail" else "skipped" if skipped is not None else "passed")
        groups[group][status] += 1
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock-url")
    args = parser.parse_args()
    try:
        mock_status = check_mock_availability(args.mock_url)
    except Exception as exc:
        mock_status = {"passed": False, "error": str(exc)}
    xml = ROOT / "tests/readiness_results.xml"
    # Remove only our own previous report so a collection error cannot reuse it.
    xml.unlink(missing_ok=True)
    # Explicit owned smoke suite: legacy live-provider tests are a separate run.
    suite = ["tests/test_demo_api.py", "tests/test_session.py", "tests/test_agent_safety.py",
             "tests/test_mock_services.py", "tests/test_trace_validation.py", "tests/test_evaluation_harness.py",
             "tests/test_demo_seed.py"]
    completed = subprocess.run([sys.executable, "-B", "-m", "pytest", *suite, "-q", "--tb=short", f"--junitxml={xml}"],
                               cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
    groups = summarize_xml(xml) if xml.exists() else {}
    test_log = completed.stdout + completed.stderr
    from evals.runner import run_evaluations
    evaluations = run_evaluations()
    report = {"mock_availability": mock_status, "pytest_exit_code": completed.returncode, "test_files": suite,
              "checks": groups, "evaluation": evaluations}
    (ROOT / "evals/latest_readiness.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "evals/latest_pytest.txt").write_text(test_log, encoding="utf-8")
    print("\nBoloAI Demo Readiness")
    print("Mode: offline application checks; live-provider correctness not measured")
    print(f"Mock available .. {'PASS' if mock_status['passed'] else 'FAIL'} ({mock_status.get('mode', mock_status.get('error'))})")
    for label, counts in groups.items():
        total = sum(counts.values())
        status = "FAIL" if counts["failed"] else "GAPS" if counts["xfail"] or counts["skipped"] else "PASS" if total else "NOT RUN"
        print(f"{label:.<17} {status} ({counts['passed']} pass, {counts['failed']} fail, {counts['xfail']} xfail, {counts['skipped']} skip)")
    print(f"Evaluation....... {evaluations['passed']}/{evaluations['total']} PASS")
    print("Details: evals/latest_readiness.json and evals/latest_pytest.txt")
    if completed.returncode not in (0, 1):
        print(f"Test runner error (exit {completed.returncode}); see log.")
    gaps = any(c["failed"] or c["xfail"] or c["skipped"] or not sum(c.values()) for c in groups.values())
    return int(not mock_status["passed"] or completed.returncode != 0 or not groups or gaps or evaluations["passed"] != evaluations["total"])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Readiness runner error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
