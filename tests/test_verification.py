import pytest
from app.services.verification import VerificationService
from app.models import VerificationStatus


def test_verification_weather_official():
    mock_weather = {
        "ok": True,
        "city": "Delhi",
        "current_temperature": 32.0,
        "source": "Open-Meteo Live API",
    }
    v = VerificationService.verify_tool_result("get_weather", mock_weather)
    assert v.status == VerificationStatus.VERIFIED_OFFICIAL
    assert v.confidence_label == "High"
    assert len(v.sources) >= 1
    assert "open-meteo" in v.sources[0]["url"]


def test_verification_official_schemes():
    mock_schemes = {
        "ok": True,
        "matches": [
            {
                "name": "UP Post-Matric Scholarship",
                "authority": "Social Welfare Dept, UP",
                "official_url": "https://scholarship.up.gov.in",
                "source_type": "VERIFIED_OFFICIAL",
                "last_verified_date": "2026-09-15",
            }
        ],
        "missing_criteria": [],
    }
    v = VerificationService.verify_tool_result("find_schemes", mock_schemes)
    assert v.status == VerificationStatus.VERIFIED_OFFICIAL
    assert v.confidence_label == "Authoritative"


def test_verification_incomplete_criteria_partially_verified():
    mock_schemes_incomplete = {
        "ok": True,
        "matches": [
            {
                "name": "UP Post-Matric Scholarship",
                "authority": "Social Welfare Dept, UP",
                "official_url": "https://scholarship.up.gov.in",
                "source_type": "VERIFIED_OFFICIAL",
            }
        ],
        "missing_criteria": ["annual family income"],
    }
    v = VerificationService.verify_tool_result("find_schemes", mock_schemes_incomplete)
    assert v.status == VerificationStatus.PARTIALLY_VERIFIED
    assert "income" in v.reason.lower()


def test_verification_demo_data_is_unverified():
    mock_demo = {
        "ok": True,
        "matches": [
            {
                "name": "DEMO Merit Scholarship",
                "authority": "Mock Demo Foundation",
                "source_type": "DEMO_DATA",
            }
        ],
        "missing_criteria": [],
    }
    v = VerificationService.verify_tool_result("find_schemes", mock_demo)
    assert v.status == VerificationStatus.UNVERIFIED
    assert "demo" in v.reason.lower()
