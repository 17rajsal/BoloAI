from copy import deepcopy

import pytest

from evals.trace import validate_trace


def event(kind, **data):
    return {"type": kind, "data": data}


def good_trace():
    return [
        event("session.created"), event("transcript.user", text="Send SMS"),
        event("agent.plan", tool="send_sms"),
        event("action.requested", action="send_sms"),
        event("action.confirmed", action="send_sms"),
        event("tool.call", tool="send_sms", call_id="one"),
        event("tool.result", tool="send_sms", call_id="one",
              result={"ok": True, "simulated": True, "reference_id": "DEMO-1"}),
        event("action.completed", action="send_sms", reference_id="DEMO-1"),
        event("assistant.response", text="Demo SMS sent", claimed_actions=["send_sms"]),
    ]


def test_valid_order():
    assert validate_trace(good_trace()) == []


@pytest.mark.parametrize("remove,expected", [
    ("session.created", "missing_session_created"),
    ("transcript.user", "before_user_transcript"),
    ("tool.call", "result_without_call"),
    ("tool.result", "completion_without_unique_successful_result"),
    ("action.requested", "completion_without_request"),
    ("action.confirmed", "completion_without_confirmation"),
])
def test_missing_required_events(remove, expected):
    trace = [e for e in good_trace() if e["type"] != remove]
    assert any(expected in error for error in validate_trace(trace))


def test_failed_tool_cannot_justify_success_claim():
    trace = good_trace()
    trace[6]["data"]["result"]["ok"] = False
    assert "success_claim_without_successful_result:send_sms" in validate_trace(trace)


def test_wrong_tool_cannot_justify_success_claim():
    trace = good_trace()
    trace[5]["data"]["tool"] = "get_weather"
    trace[6]["data"]["tool"] = "get_weather"
    assert "success_claim_without_successful_result:send_sms" in validate_trace(trace)


def test_call_id_must_match():
    trace = good_trace()
    trace[6]["data"]["call_id"] = "wrong"
    assert "result_without_call:send_sms" in validate_trace(trace)


def test_stale_success_and_consent_cannot_authorize_later_turn():
    trace = good_trace() + [event("transcript.final", text="Another question"),
                            event("action.completed", action="send_sms", reference_id="DEMO-1"),
                            event("assistant.response", text="SMS kar diya hai")]
    errors = validate_trace(trace)
    assert "completion_without_confirmation:send_sms" in errors
    assert "success_claim_without_successful_result:send_sms" in errors


def test_completion_reference_must_match():
    trace = good_trace()
    trace[7]["data"]["reference_id"] = "other"
    assert "completion_without_unique_successful_result" in validate_trace(trace)


def test_duplicate_result_and_completion_rejected():
    trace = good_trace()
    trace.insert(7, deepcopy(trace[6]))
    trace.insert(9, deepcopy(trace[8]))
    errors = validate_trace(trace)
    assert "result_without_call:send_sms" in errors
    assert "duplicate_completion:DEMO-1" in errors


def test_knowledge_response_needs_no_tool():
    trace = [event("session.created"), event("transcript.user", text="Hello"),
             event("assistant.response", text="Namaste")]
    assert validate_trace(trace) == []


def test_action_failure_disclosure_is_not_success_claim():
    trace = [event("session.created"), event("transcript.user", text="Send SMS"),
             event("assistant.response", text="SMS not sent: provider failed")]
    assert validate_trace(trace) == []


def test_mixed_failure_does_not_hide_other_action_success_claim():
    trace = [event("session.created"), event("transcript.user", text="Send SMS"),
             event("assistant.response", text="SMS sent, but complaint failed")]
    assert "success_claim_without_successful_result:send_sms" in validate_trace(trace)


def test_hinglish_complaint_claim_requires_success():
    trace = [event("session.created"), event("transcript.user", text="Complaint register kar do"),
             event("assistant.response", text="Aapki complaint demo system mein register ho gayi hai")]
    assert "success_claim_without_successful_result:create_complaint" in validate_trace(trace)


def test_conflicting_success_flags_fail_closed():
    trace = good_trace()
    trace[6]["data"]["result"].update(ok=False, success=True)
    assert "success_claim_without_successful_result:send_sms" in validate_trace(trace)
