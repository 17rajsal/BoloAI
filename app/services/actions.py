"""Authoritative action outcomes and per-session, per-turn execution lifecycle.

Cache scope matches the in-memory session store. An explicit new turn_id permits
an intentional repeat/retry; duplicates of the same turn reuse the prior outcome.
"""
from copy import deepcopy
import json
import re
from typing import Any, Callable

from ..store import Session, add_event
from .idempotency import generate_action_key

_ACTION_OBSERVATIONS: dict[str, dict] = {}


def action_readiness(action: str, default_state: str) -> dict:
    observed = _ACTION_OBSERVATIONS.get(action, {})
    state = observed.get("state", default_state)
    return {"state": state, "configured": default_state == "LIVE", "ready": state != "ERROR",
            "last_error": observed.get("error"), "availability": "last observed result; no active provider probe"}


def normalize_action_result(action: str, raw: Any) -> dict[str, Any]:
    """Only an explicit boolean ok=True can authorize completion.

Conflicting flags, errors, failure statuses and malformed simulation flags fail
closed. Keep provider-specific fields on success; failure cannot expose a
successful reference, SLA or provider message masquerading as success.
"""
    if not isinstance(raw, dict):
        return {"ok": False, "action": action, "simulated": False,
                "reference_id": None, "error": "Provider returned an invalid result"}
    simulated = raw.get("simulated", raw.get("demo", False))
    status = str(raw.get("status", "")).upper()
    success = (raw.get("ok") is True and raw.get("success", True) is True
               and not raw.get("error") and type(simulated) is bool
               and status not in {"FAILED", "FAILURE", "ERROR", "REJECTED", "UNDELIVERED", "CANCELLED"})
    if not success:
        return {"ok": False, "action": action, "simulated": simulated is True,
                "reference_id": None, "status": "FAILED",
                "error": str(raw.get("error") or "Provider did not explicitly confirm success")}
    result = deepcopy(raw)
    reference = result.get("reference_id")
    result.update(ok=True, action=action, simulated=simulated,
                  reference_id=reference.strip() if isinstance(reference, str) and reference.strip() else None)
    if simulated:
        result["status"] = "SIMULATED"
    else:
        result.setdefault("status", "COMPLETED")
    return result


def action_allowed(action: str, text: str, intent: str, flags: dict) -> bool:
    if flags.get("prohibited"):
        return False
    expected = {"send_sms": "SEND_SMS_LINK", "create_complaint": "FILE_COMPLAINT",
                "request_document_upload": "REQUEST_UPLOAD"}
    if expected.get(action) != intent:
        return False
    return bool(re.search(r"\b(send|register|file|dispatch|bhej|bhejo|karo|kar do|darj|please|karna|upload|verify|check|link)\b|भेज|दर्ज|कर दो|करो|करना", text.lower()))


def execute_action(session: Session, action: str, args: dict,
                   executor: Callable[[str, dict], dict]) -> dict:
    payload = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    key = generate_action_key(session.id, action, payload, session.active_turn_id)
    with session.turn_lock:
        if key in session.action_executions:
            previous = session.action_executions[key]
            add_event(session.id, "action.reused", {"action": action,
                      "action_id": previous["action_id"], "state": previous["state"],
                      "simulated": previous["simulated"]})
            return deepcopy(previous)
        action_id = f"{session.id}:action-{len(session.action_executions) + 1}"
        base = {"action": action, "action_id": action_id, "turn_id": session.active_turn_id}
        requested = {**base, "state": "REQUESTED", "args": deepcopy(args)}
        session.actions_requested.append(requested)
        add_event(session.id, "action.requested", requested)
        confirmed = {**base, "state": "CONFIRMED", "confirmed_by": "caller_instruction"}
        session.actions_confirmed.append(confirmed)
        add_event(session.id, "action.confirmed", confirmed)
        session.set_status("tool_running")
        add_event(session.id, "tool.call", {**base, "call_id": action_id,
                  "tool": action, "args": args, "state": "EXECUTING"})
        try:
            raw = executor(action, args)
        except Exception:
            raw = {"ok": False, "error": "Action provider unavailable; please try again later"}
        result = normalize_action_result(action, raw)
        _ACTION_OBSERVATIONS[action] = {"state": "SIMULATED" if result["ok"] and result["simulated"] else "LIVE" if result["ok"] else "ERROR",
                                        "error": result.get("error")}
        result.update(action_id=action_id, state="COMPLETED" if result["ok"] else "FAILED")
        add_event(session.id, "tool.result", {**base, "call_id": action_id, "tool": action, "result": deepcopy(result)})
        session.action_executions[key] = deepcopy(result)
        if result["ok"]:
            session.actions_completed.append(deepcopy(result))
            add_event(session.id, "action.completed", {**base, **result})
        else:
            session.actions_failed.append(deepcopy(result))
            add_event(session.id, "action.failed", {**base, **result})
        return result


def tracking_summary(session: Session, tracking_id: str | None = None) -> str:
    previous = session.read_results.get("track_courier", {})
    if previous.get("ok") is not True or (tracking_id and previous.get("tracking_id") != tracking_id):
        return ""
    hub = previous.get("current_location") or previous.get("current_hub")
    status = previous.get("status")
    if not hub or not status:
        return ""
    prefix = "Demo tracking ke anusaar" if previous.get("simulated") or previous.get("demo") else "Tracking ke anusaar"
    return f"{prefix} aapka parcel {hub} par hai; status {status}. "


def action_answer(session: Session, action: str, result: dict) -> str:
    if not result["ok"]:
        if action == "create_complaint":
            return tracking_summary(session, session.context.get("tracking_id")) + "Complaint register nahi ho paayi. Complaint service mein dikkat hai; baad mein phir koshish kar sakte hain."
        if action in {"send_sms", "request_document_upload"}:
            return "SMS bhejne mein dikkat aa rahi hai. Is action ko successful nahi maana gaya; baad mein phir koshish kar sakte hain."
        return "Action poora nahi ho paaya. Seva mein dikkat hai; baad mein phir koshish kar sakte hain."
    if result["simulated"]:
        label = "complaint" if action == "create_complaint" else "upload-link SMS" if action == "request_document_upload" else "SMS" if action == "send_sms" else "action"
        answer = f"Demo mode mein {label} action simulate ho gaya hai. Koi real provider action nahi hua."
    elif action == "send_sms":
        answer = "SMS provider ne message bhejne ka request accept kar liya hai. Delivery ki pushti abhi nahi hui hai."
    elif action == "create_complaint":
        answer = "Aapki complaint register ho gayi hai."
    elif action == "request_document_upload":
        answer = "SMS provider ne photo upload link bhejne ka request accept kar liya hai."
    else:
        answer = "Provider ne action poora hone ki pushti ki hai."
    if result.get("reference_id"):
        answer += f" Reference ID {result['reference_id']}."
    else:
        answer += " Provider ne reference ID nahi diya hai."
    return answer
