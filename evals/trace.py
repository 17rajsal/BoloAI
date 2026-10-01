"""Operational trace checks only; no private reasoning is inspected.

Accepts BoloAI {type, data} events and transcript.user/transcript.final aliases.
Prefer call_id and reference_id for correlation. Legacy traces without IDs use
tool-name FIFO within a turn; ambiguous completions fail closed. Authorization
is matched by action name and consumed on completion, not by action arguments.
Explicit action.requested and action.confirmed events are evidence of recorded
authorization, not proof that the caller actually consented.
"""
import re
from collections import defaultdict
from typing import Any, Iterable

ACTION_ALIASES = {"REGISTER_COMPLAINT": "create_complaint", "SEND_SMS": "send_sms"}
ACTIONS = {"create_complaint", "send_sms", "external_submission"}


def claims_success(text: str) -> set[str]:
    text = text.lower()
    # Conservative, documented heuristic; structured claims are preferred.
    found = set()
    for clause in re.split(r"[.;,\n]|\bbut\b|\blekin\b", text):
        if re.search(r"\b(not sent|not registered|failed|nahi|nahin|could not)\b", clause):
            continue
        if re.search(r"(?:sms|message).*(?:sent|kar diya|bhej diya)|sent.*(?:sms|message)", clause):
            found.add("send_sms")
        if re.search(r"complaint.*(?:registered|register ho|darj ho|successfully)|registered.*complaint", clause):
            found.add("create_complaint")
    return found


def validate_trace(events: Iterable[dict[str, Any]],
                   confirmation_required: set[str] | None = None) -> list[str]:
    required = ACTIONS if confirmation_required is None else confirmation_required
    errors: list[str] = []
    calls: dict[str, list[dict]] = defaultdict(list)
    requested: set[str] = set()
    confirmed: set[str] = set()
    successes: list[tuple[str, dict]] = []
    completed_refs: set[str] = set()
    started = False
    user_seen = False

    def finish_turn():
        for tool, pending in calls.items():
            if pending:
                errors.append(f"unresolved_tool_call:{tool}")
        calls.clear()

    for index, event in enumerate(events):
        kind, data = event.get("type"), event.get("data") or {}
        if kind == "session.created":
            if started or index != 0:
                errors.append("session_created_out_of_order")
            started = True
            continue
        if not started:
            errors.append("missing_session_created")
            started = True  # report once
        if kind in {"transcript.user", "transcript.final"}:
            finish_turn()
            requested.clear()
            confirmed.clear()
            successes.clear()
            completed_refs.clear()
            user_seen = True
        elif kind in {"agent.plan", "tool.call", "tool.result"} and not user_seen:
            errors.append(f"before_user_transcript:{kind}")
        if kind == "tool.call":
            tool = data.get("tool", "")
            if not tool:
                errors.append("missing_tool_name")
            calls[tool].append(data)
        elif kind == "tool.result":
            tool = data.get("tool", "")
            pending = calls[tool]
            match = next((c for c in pending if not data.get("call_id")
                          or c.get("call_id") == data["call_id"]), None)
            if match is None:
                errors.append(f"result_without_call:{tool}")
            else:
                pending.remove(match)
                result = data.get("result") or {}
                if result.get("ok") is not False and result.get("success") is not False and (
                        result.get("ok") is True or result.get("success") is True):
                    successes.append((tool, result))
        elif kind == "action.requested":
            requested.add(data.get("action", ""))
        elif kind == "action.confirmed":
            action = data.get("action", "")
            if action not in requested:
                errors.append(f"confirmation_without_request:{action}")
            else:
                confirmed.add(action)
        elif kind == "action.completed":
            ref = data.get("reference_id")
            action = data.get("action") or ACTION_ALIASES.get(data.get("action_type"))
            candidates = [(tool, result) for tool, result in successes
                          if tool in ACTIONS and (not action or tool == action)
                          and (not ref or result.get("reference_id") == ref)]
            if len(candidates) != 1:
                errors.append("completion_without_unique_successful_result")
            else:
                action = candidates[0][0]
            if not action or action not in requested:
                errors.append(f"completion_without_request:{action}")
            if action in required and action not in confirmed:
                errors.append(f"completion_without_confirmation:{action}")
            if ref and ref in completed_refs:
                errors.append(f"duplicate_completion:{ref}")
            if ref:
                completed_refs.add(ref)
            requested.discard(action)
            confirmed.discard(action)
        elif kind == "assistant.response":
            claims = set(data.get("claimed_actions", [])) | claims_success(data.get("text", ""))
            for action in claims:
                if not any(tool == action for tool, _ in successes):
                    errors.append(f"success_claim_without_successful_result:{action}")
            finish_turn()
            # Results from a prior assistant response cannot justify a new claim.
            successes.clear()
            user_seen = False
    finish_turn()
    return errors
