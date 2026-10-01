from evals.cases import CASES
from evals.runner import evaluate_case
from evals.cases import Case


def test_case_inventory():
    assert len(CASES) >= 30
    assert len({c.id for c in CASES}) == len(CASES)
    assert {"Hindi", "Hinglish", "English"} <= {c.language for c in CASES}
    assert {"general_knowledge", "government_schemes", "weather", "education", "uncertain_claim",
            "courier", "sms", "ambiguous", "credential"} <= {c.expected_category for c in CASES}


def test_harness_detects_wrong_expectation(client):
    case = Case("deliberate-mismatch", "Namaste", "weather", True, "get_weather", verification_required=True)
    result = evaluate_case(client, case)
    assert result["passed"] is False
    assert any("missing tool" in error for error in result["errors"])


def test_harness_accepts_supported_weather_behavior(client):
    case = next(c for c in CASES if c.id == "weather-01")
    assert evaluate_case(client, case)["passed"] is True
