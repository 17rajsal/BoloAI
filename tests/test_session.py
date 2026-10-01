import pytest
from app.store import create_session, get_session, ensure_session, add_event


def test_create_session():
    s = create_session(caller="+919876543210", language="hi-IN")
    assert s.id.startswith("bolo-")
    assert s.caller == "+919876543210"
    assert s.language == "hi-IN"
    assert s.call_status == "idle"
    assert len(s.events) >= 1
    assert s.events[0]["type"] == "session.created"


def test_ensure_and_get_session():
    custom_id = "test-session-custom-123"
    s1 = ensure_session(custom_id, caller="+919123456789")
    assert s1.id == custom_id
    assert s1.caller == "+919123456789"

    s2 = get_session(custom_id)
    assert s2.id == custom_id


def test_context_persistence_across_turns():
    s = create_session(caller="+919876543210")
    s.update_context({"state": "Uttar Pradesh", "course": "BTech"})
    assert s.context["state"] == "Uttar Pradesh"
    assert s.context["course"] == "BTech"

    # Add further context in later turn
    s.update_context({"year": "Second Year", "income": 180000.0})
    assert s.context["state"] == "Uttar Pradesh"
    assert s.context["course"] == "BTech"
    assert s.context["year"] == "Second Year"
    assert s.context["income"] == 180000.0


def test_event_logging():
    s = create_session()
    add_event(s.id, "tool.call", {"tool": "get_weather", "city": "Jaipur"})
    add_event(s.id, "tool.result", {"ok": True, "temp": 28.5})

    fetched = get_session(s.id)
    types = [e["type"] for e in fetched.events]
    assert "tool.call" in types
    assert "tool.result" in types
