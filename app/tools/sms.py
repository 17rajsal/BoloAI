from datetime import datetime, timezone
import re
from typing import Any, Dict
from uuid import uuid4

from .. import config

# Observed readiness, scoped to the provider configuration. Health does not send probes.
_PROVIDER_OBSERVATIONS: dict[tuple, dict] = {}


def _configuration_key() -> tuple:
    return (config.SMS_PROVIDER, config.DEMO_MODE, config.has_exotel(), bool(config.EXOTEL_EXOPHONE))


def sms_readiness() -> dict:
    configured = config.SMS_PROVIDER == "exotel" and config.has_exotel() and bool(config.EXOTEL_EXOPHONE)
    simulated = config.DEMO_MODE or config.SMS_PROVIDER == "mock"
    state = "SIMULATED" if simulated else "LIVE" if configured else "ERROR"
    observed = _PROVIDER_OBSERVATIONS.get(_configuration_key(), {})
    return {"configured": configured, "ready": state != "ERROR" and observed.get("state") != "ERROR",
            "state": observed.get("state", state), "mode": "mock-sms" if simulated else "exotel-sms",
            "last_error": observed.get("error"), "availability": "last observed result; no active provider probe"}


def send_sms(phone: str, message: str) -> Dict[str, Any]:
    """Explicit demo simulation or validated provider acceptance; never silent fallback."""
    ts = datetime.now(timezone.utc).isoformat()
    cleaned_phone = re.sub(r"[\s()-]", "", phone) if isinstance(phone, str) else ""
    masked_phone = cleaned_phone[:3] + "****" + cleaned_phone[-3:] if len(cleaned_phone) >= 10 else ""
    simulated = config.DEMO_MODE or config.SMS_PROVIDER == "mock"

    def failure(error: str) -> dict:
        _PROVIDER_OBSERVATIONS[_configuration_key()] = {"state": "ERROR", "error": error}
        return {"ok": False, "simulated": simulated, "reference_id": None,
                "status": "FAILED", "error": error, "phone": masked_phone, "timestamp": ts}

    if not re.fullmatch(r"\+?[1-9]\d{9,14}", cleaned_phone) or not isinstance(message, str) or not message.strip():
        # Input validation says nothing about whether the provider is available.
        return {"ok": False, "simulated": simulated, "reference_id": None,
                "status": "FAILED", "error": "A valid phone number and message are required"}
    if simulated:
        _PROVIDER_OBSERVATIONS[_configuration_key()] = {"state": "SIMULATED"}
        return {"ok": True, "simulated": True, "tool_label": "SIMULATED_ACTION",
                "provider": "Mock SMS Gateway (Simulated)", "status": "SIMULATED_DISPATCHED",
                "phone": masked_phone, "message": message, "reference_id": f"SIM-SMS-{uuid4().hex[:12]}",
                "timestamp": ts, "notice": "Demo Mode: SMS was simulated and was not sent to a cellular carrier."}
    if config.SMS_PROVIDER != "exotel":
        return failure("Selected SMS provider is not supported")
    if not config.has_exotel() or not config.EXOTEL_EXOPHONE:
        return failure("SMS provider configuration is incomplete")
    import httpx
    try:
        response = httpx.post(
            f"https://api.exotel.com/v1/Accounts/{config.EXOTEL_ACCOUNT_SID}/Sms/send.json",
            auth=(config.EXOTEL_API_KEY, config.EXOTEL_API_TOKEN),
            data={"From": config.EXOTEL_EXOPHONE, "To": cleaned_phone, "Body": message}, timeout=5.0)
        if not 200 <= response.status_code < 300:
            return failure("SMS provider rejected the request")
        body = response.json()
        data = body.get("SMSMessage") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            return failure("SMS provider did not return a valid acknowledgement")
        reference = data.get("Sid")
        provider_state = str(data.get("Status", "accepted")).lower()
        if (not isinstance(reference, str) or not reference.strip() or data.get("ErrorCode")
                or provider_state not in {"accepted", "queued", "sending", "sent", "delivered"}):
            return failure("SMS provider did not confirm acceptance with a reference ID")
        _PROVIDER_OBSERVATIONS[_configuration_key()] = {"state": "LIVE"}
        return {"ok": True, "simulated": False, "provider": "Exotel SMS Gateway",
                "status": provider_state.upper(), "phone": masked_phone, "message": message,
                "reference_id": reference.strip(), "timestamp": ts}
    except httpx.TimeoutException:
        return failure("SMS provider timed out; delivery could not be confirmed")
    except Exception:
        return failure("SMS provider unavailable or returned an invalid response")
