import pytest
from app.store import create_session, get_session
from app.agent.orchestrator import AgentOrchestrator


def test_agent_weather_query():
    s = create_session()
    res = AgentOrchestrator.respond(s.id, "Delhi mein kal baarish hogi?")
    assert "Delhi" in res["answer"]
    assert "baarish" in res["answer"].lower()
    assert "get_weather" in res["tools_used"]
    assert res["verified"] is True


def test_agent_context_persistence_multiturn():
    s = create_session()

    # Turn 1: Caller mentions state and course
    res1 = AgentOrchestrator.respond(s.id, "I am from Uttar Pradesh and studying BTech.")
    session_after_1 = get_session(s.id)
    assert session_after_1.context.get("state") == "Uttar Pradesh"
    assert session_after_1.context.get("course") == "BTech"

    # Turn 2: Later caller asks "Mere state ki schemes batao" without repeating UP
    res2 = AgentOrchestrator.respond(s.id, "Mere state ki schemes batao.")
    session_after_2 = get_session(s.id)
    assert session_after_2.context.get("state") == "Uttar Pradesh"
    assert "Uttar Pradesh" in res2["answer"] or "UP" in res2["answer"]


def test_agent_safety_blocks_otp_prompt():
    s = create_session()
    res = AgentOrchestrator.respond(s.id, "Mera OTP 948201 hai, account verify karo.")
    assert "OTP" in res["answer"]
    assert "share na karein" in res["answer"].lower() or "nahi maangta" in res["answer"].lower()
    assert res["metadata"].get("safety_block") is True


def test_agent_courier_tracking_and_complaint_action():
    s = create_session()

    # Step 1: Track courier
    res1 = AgentOrchestrator.respond(s.id, "Mera parcel ABC123 kaha hai?")
    assert "track_courier" in res1["tools_used"]
    assert "ABC123" in res1["answer"]
    assert "delay" in res1["answer"].lower()

    # Step 2: Register complaint
    res2 = AgentOrchestrator.respond(s.id, "Ha, complaint register kar do.")
    assert "create_complaint" in res2["tools_used"]
    assert "BOL-CMP-" in res2["answer"]
    assert res2["action_completed"] is not None
