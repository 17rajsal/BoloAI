import importlib.util
from pathlib import Path

from evals.sandbox import isolated_app


def test_seed_is_deterministic_and_captures_observed_sessions():
    path = Path(__file__).resolve().parents[1] / "scripts/demo_seed.py"
    spec = importlib.util.spec_from_file_location("demo_seed_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with isolated_app() as client:
        first = module.seed(client, deterministic=True)
    with isolated_app() as client:
        second = module.seed(client, deterministic=True)
    assert first == second
    assert [item["scenario"] for item in first["sessions"]] == ["scholarship", "weather", "courier"]
    scholarship = first["sessions"][0]["session"]["context"]
    assert scholarship["state"] == "Uttar Pradesh"
    assert scholarship["course"] == "BTech"
    assert str(scholarship["year"]).lower() in {"2", "second", "second year"}
    assert scholarship["income"] == 180000
    assert first["sessions"][2]["responses"][-1]["action_completed"]["reference_id"].startswith("DEMO-CMP-")
