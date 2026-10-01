import pytest
from app.services.safety import SafetyService


def test_reject_otp_and_pin_leaks():
    assert SafetyService.inspect_text_for_sensitive_leak("Mera OTP 492019 hai") is True
    assert SafetyService.inspect_text_for_sensitive_leak("Enter your UPI PIN to continue") is True
    assert SafetyService.inspect_text_for_sensitive_leak("ATM PIN batayein") is True
    assert SafetyService.inspect_text_for_sensitive_leak("Card ka CVV kya hai") is True
    assert SafetyService.inspect_text_for_sensitive_leak("Mera password change karo") is True

    # Safe utterances should not be flagged
    assert SafetyService.inspect_text_for_sensitive_leak("Delhi mein mausam kaisa hai") is False
    assert SafetyService.inspect_text_for_sensitive_leak("Scholarship scheme bataiye") is False


def test_high_risk_disclaimers():
    # Emergency / suicide crisis check
    cat, disclaimer = SafetyService.check_high_risk_intent("I want to commit suicide")
    assert cat == "EMERGENCY_CRISIS"
    assert "14416" in disclaimer or "112" in disclaimer

    # Acute medical condition check
    cat, disclaimer = SafetyService.check_high_risk_intent("Mujhe severe chest pain aur heart attack ke symptoms hain")
    assert cat == "MEDICAL_ADVICE"
    assert "108" in disclaimer or "doctor" in disclaimer

    # Safe utterance
    cat, disclaimer = SafetyService.check_high_risk_intent("UP mein BTech scholarship kya hai?")
    assert cat is None
    assert disclaimer is None


def test_action_confirmation_rules():
    assert SafetyService.requires_confirmation("create_complaint") is True
    assert SafetyService.requires_confirmation("send_sms") is True
    assert SafetyService.requires_confirmation("get_weather") is False
