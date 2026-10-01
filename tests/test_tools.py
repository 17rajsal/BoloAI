import pytest
from app.tools.registry import execute_tool, ToolRegistry
from app.tools.weather import get_weather
from app.tools.schemes import find_schemes, load_schemes
from app.tools.courier import track_courier, create_complaint
from app.tools.sms import send_sms


def test_tool_registry_schemas():
    schemas = ToolRegistry.get_schemas()
    assert len(schemas) >= 5
    names = [s["name"] for s in schemas]
    assert "get_weather" in names
    assert "find_schemes" in names
    assert "track_courier" in names
    assert "create_complaint" in names
    assert "send_sms" in names


def test_weather_tool_live():
    res = get_weather("Delhi")
    assert res["ok"] is True
    assert "temperature" in res or "current_temperature" in res
    assert res["source"] == "Open-Meteo Live API"
    assert "city" in res


def test_schemes_normalized_matching():
    # Matching UP BTech with low income
    res = find_schemes(state="Uttar Pradesh", education="BTech", income=200000.0, include_demo=False)
    assert res["ok"] is True
    assert res["count"] >= 1
    # Check schema fields on matched records
    top = res["matches"][0]
    assert "name" in top
    assert "authority" in top
    assert "eligibility" in top
    assert "benefit" in top
    assert "official_url" in top
    assert top["source_type"] == "VERIFIED_OFFICIAL"


def test_schemes_distinguish_demo_data():
    # Load with include_demo=True
    all_schemes = load_schemes(include_demo=True)
    demo_found = any(s["source_type"] == "DEMO_DATA" for s in all_schemes)
    verified_found = any(s["source_type"] == "VERIFIED_OFFICIAL" for s in all_schemes)
    assert demo_found is True
    assert verified_found is True


def test_courier_tracking_and_action():
    # Information tool
    track_res = track_courier("ABC123")
    assert track_res["ok"] is True
    assert track_res["simulated"] is True
    assert track_res["status"] == "DELAYED"

    # Action tool
    complaint_res = create_complaint("ABC123", reason="Delayed beyond SLA")
    assert complaint_res["ok"] is True
    assert complaint_res["simulated"] is True
    assert complaint_res["status"] == "REGISTERED"
    assert complaint_res["reference_id"].startswith("BOL-CMP-")


def test_sms_action_simulated_mode():
    res = send_sms("9876543210", "Test official scholarship link: https://scholarships.gov.in")
    assert res["ok"] is True
    assert res["simulated"] is True
    assert "SIM-SMS-" in res["reference_id"]
    # Ensure phone number is masked in the output
    assert "****" in res["phone"]
