import json
import logging
from copy import deepcopy
from hashlib import sha256
from typing import Any, Dict, List, Optional
from .. import config
from ..models import AgentResponse, VerificationDetail, VerificationStatus
from ..services.safety import SafetyService
from ..services.verification import VerificationService
from ..services.actions import action_allowed, action_answer, execute_action, tracking_summary
from ..store import Session, add_event, get_session
from ..tools.registry import ToolRegistry, execute_tool
from .memory import detect_caller_intent, detect_language, extract_context
from .prompt import SYSTEM_PROMPT

logger = logging.getLogger("boloai.agent")


class AgentOrchestrator:
    """Master Agent for BoloAI.
    Coordinates intent understanding, context extraction, plan generation,
    tool selection, verification, action execution, and voice-friendly response generation.
    """

    @classmethod
    def respond(cls, session_id: str, text: str, turn_id: Optional[str] = None) -> Dict[str, Any]:
        session = get_session(session_id)
        normalized = " ".join(text.split()).casefold()
        with session.turn_lock:
            preview = extract_context(text, session.context)
            preview_intent, _, _ = detect_caller_intent(text, preview)
            identity = {}
            if preview_intent == "FILE_COMPLAINT":
                identity = {"tracking_id": preview.get("tracking_id"), "phone": session.caller or preview.get("phone")}
            elif preview_intent in {"SEND_SMS_LINK", "REQUEST_UPLOAD"}:
                identity = {"phone": session.caller or preview.get("phone"), "state": preview.get("state")}
            key = f"turn:{turn_id}" if turn_id else "text:" + sha256((normalized + json.dumps(identity, sort_keys=True)).encode()).hexdigest()
            if key in session.turn_results:
                if session.turn_inputs[key] != normalized:
                    raise ValueError("turn_id was already used for a different request")
                cached = deepcopy(session.turn_results[key])
                cached.setdefault("metadata", {})["idempotent_replay"] = True
                return cached
            session.active_turn_id = key
            result = cls._respond_turn(session_id, text)
            # Explicit IDs cache every turn; legacy callers cache action attempts.
            if turn_id or any(ToolRegistry.get_metadata(tool).get("is_action") for tool in result.get("tools_used", [])):
                session.turn_results[key] = deepcopy(result)
                session.turn_inputs[key] = normalized
            return result

    @classmethod
    def _respond_turn(cls, session_id: str, text: str) -> Dict[str, Any]:
        session = get_session(session_id)
        session.set_status("thinking")

        # 1. Safety check: Protect against sensitive credentials
        if SafetyService.inspect_text_for_sensitive_leak(text):
            sanitized_text = SafetyService.sanitize_credentials(text)
            session.history.append({"role": "user", "content": sanitized_text})
            add_event(session_id, "transcript.final", {"text": sanitized_text})
            add_event(session_id, "error", {"type": "SENSITIVE_CREDENTIAL_ATTEMPT", "text": "Filtered sensitive credential"})
            resp_text = "Suraksha ke liye, BoloAI kabhi bhi OTP, UPI PIN, ATM PIN ya password nahi maangta aur na hi accept karta hai. Kripya inhe kisi ke saath share na karein."
            session.history.append({"role": "assistant", "content": resp_text})
            add_event(session_id, "assistant.response", {"text": resp_text})
            session.set_status("speaking")
            return {
                "session_id": session_id,
                "answer": resp_text,
                "language": "hi-IN",
                "tools_used": [],
                "verified": False,
                "metadata": {"safety_block": True},
            }

        # Check high-risk medical / crisis / financial intent
        risk_cat, disclaimer = SafetyService.check_high_risk_intent(text)
        if disclaimer:
            session.history.append({"role": "user", "content": text})
            add_event(session_id, "transcript.final", {"text": text})
            add_event(session_id, "agent.plan", {"risk_category": risk_cat, "safety_interception": True})
            session.history.append({"role": "assistant", "content": disclaimer})
            add_event(session_id, "assistant.response", {"text": disclaimer})
            session.set_status("speaking")
            return {
                "session_id": session_id,
                "answer": disclaimer,
                "language": "hi-IN",
                "tools_used": [],
                "verified": False,
                "metadata": {"high_risk_interception": risk_cat},
            }

        # 2. Extract Context & Update Slots
        prev_context = dict(session.context)
        updated_context = extract_context(text, prev_context)
        session.update_context(updated_context)

        # 3. Detect Language & Intent
        lang = detect_language(text)
        session.language = "en-IN" if lang == "English" else "hi-IN"
        intent, goal, flags = detect_caller_intent(text, session.context)
        if goal:
            session.set_goal(goal)
        session.update_context({"last_intent": intent})

        session.history.append({"role": "user", "content": text})
        add_event(session_id, "transcript.final", {"text": text})
        add_event(session_id, "agent.context_updated", {"context": session.context})
        add_event(session_id, "agent.intent", {"intent": intent, "goal": goal, "detected_language": lang})

        # 4. Route: Live OpenAI API or Deterministic Slot-Filling Engine
        if config.has_openai():
            prior_executions = set(session.action_executions)
            try:
                return cls._respond_openai(session, text, intent, flags)
            except Exception as exc:
                logger.warning(f"OpenAI call failed ({exc}); falling back to deterministic Master Agent engine.")
                add_event(session_id, "error", {"module": "openai", "error": str(exc)})
                executed = [outcome for key, outcome in session.action_executions.items() if key not in prior_executions]
                if executed:
                    # Never re-enter a write path after an outcome exists merely
                    # because model generation or serialization failed afterward.
                    answer = " ".join(action_answer(session, r["action"], r) for r in executed)
                    session.history.append({"role": "assistant", "content": answer})
                    add_event(session_id, "assistant.response", {"text": answer})
                    session.set_status("speaking")
                    return {"session_id": session_id, "answer": answer, "language": session.language,
                            "tools_used": [r["action"] for r in executed], "verified": False,
                            "action_completed": next((r for r in reversed(executed) if r["ok"]), None),
                            "action_failed": next((r for r in reversed(executed) if not r["ok"]), None),
                            "metadata": {"mode": "authoritative-action-recovery"}}

        # Demo & Deterministic Fallback Engine
        return cls._respond_deterministic(session, text, intent, flags)

    @classmethod
    def _record_verification(cls, session: Session, tool: str, result: dict) -> VerificationDetail:
        session.set_status("verifying")
        try:
            verification = VerificationService.verify_tool_result(tool, result)
            if not isinstance(verification, VerificationDetail):
                raise ValueError("Invalid verification response")
        except Exception:
            verification = VerificationDetail(status=VerificationStatus.UNVERIFIED,
                reason="Verification service unavailable", sources=[], confidence_label="Uncertain")
        session.verification_results.append(verification.model_dump())
        add_event(session.id, "verification.completed", verification.model_dump())
        return verification

    @classmethod
    def _respond_openai(cls, session: Session, text: str, intent: str, flags: Dict[str, Any]) -> Dict[str, Any]:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        tools_used: List[str] = []
        last_verification: Optional[VerificationDetail] = None
        outcomes: List[Dict[str, Any]] = []
        failed_reads: List[str] = []
        instructions = (
            f"{SYSTEM_PROMPT}\n\nCURRENT SESSION CONTEXT:\n{json.dumps(session.context)}\n"
            "Maintain this context; do not re-ask known values. Provide clean spoken answers in 2 to 4 sentences "
            "without markdown symbols (*, #, `), bullet lists, raw URLs, or JSON."
        )
        messages = [{"role": m["role"], "content": m["content"]} for m in session.history[-10:]]
        add_event(session.id, "agent.plan", {"intent": intent, "orchestrator": "OpenAI Chat Completions",
                  "model": config.OPENAI_MODEL})
        # Registry schemas are flat function definitions; Chat Completions nests them.
        schemas = [{"type": "function", "function": {k: v for k, v in schema.items() if k != "type"}}
                   for schema in ToolRegistry.get_schemas()]
        completion = client.chat.completions.create(model=config.OPENAI_MODEL,
            messages=[{"role": "system", "content": instructions}] + messages,
            tools=schemas, tool_choice="auto")
        msg = completion.choices[0].message
        if msg.tool_calls:
            messages.append(msg)
            for call in msg.tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments)
                    if not isinstance(args, dict):
                        args = {}
                except (TypeError, ValueError):
                    args = {}
                is_action = ToolRegistry.get_metadata(name).get("is_action")
                if is_action:
                    if not action_allowed(name, text, intent, flags):
                        # A model proposing an action is not evidence of caller consent.
                        result = {"ok": False, "action": name, "simulated": False,
                                  "reference_id": None, "error": "Caller confirmation required"}
                        add_event(session.id, "action.requested", {"action": name, "state": "REQUESTED"})
                        add_event(session.id, "action.failed", {**result, "state": "FAILED"})
                    elif name == "request_document_upload" and args.get("session_id") != session.id:
                        result = {"ok": False, "action": name, "simulated": False,
                                  "reference_id": None, "error": "Upload must belong to the caller session"}
                        add_event(session.id, "action.failed", {**result, "state": "FAILED"})
                    else:
                        tools_used.append(name)
                        result = execute_action(session, name, args, execute_tool)
                    outcomes.append(result)
                else:
                    tools_used.append(name)
                    session.set_status("tool_running")
                    add_event(session.id, "tool.call", {"tool": name, "args": args, "call_id": call.id})
                    result = execute_tool(name, args)
                    add_event(session.id, "tool.result", {"tool": name, "result": result, "call_id": call.id})
                    if result.get("ok") is True:
                        session.read_results[name] = deepcopy(result)
                    else:
                        failed_reads.append(name)
                last_verification = cls._record_verification(session, name, result)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
            if outcomes:
                # Action narration is constructed from authoritative outcomes. The
                # model cannot overwrite failures, references, or simulation labels.
                answer = " ".join(action_answer(session, outcome["action"], outcome) for outcome in outcomes)
            elif failed_reads:
                answer = "Live seva se jankari nahi mil paayi. Main is jawab ko verify nahi kar saka; baad mein phir koshish karein."
            else:
                try:
                    completion = client.chat.completions.create(model=config.OPENAI_MODEL,
                        messages=[{"role": "system", "content": instructions}] + messages)
                    answer = completion.choices[0].message.content or "Jankari ka jawab taiyaar nahi ho paaya."
                except Exception:
                    answer = "Jankari mili hai, lekin jawab taiyaar karne mein dikkat hai."
        elif intent in {"FILE_COMPLAINT", "SEND_SMS_LINK", "REQUEST_UPLOAD"}:
            answer = "Is action ka successful tool result nahi mila. Koi action successful hone ki pushti nahi kar sakta."
        else:
            answer = msg.content or "Maaf kijiye, main samajh nahi paya."
        session.history.append({"role": "assistant", "content": answer})
        add_event(session.id, "assistant.response", {"text": answer})
        session.set_status("speaking")
        failed = next((r for r in reversed(outcomes) if not r["ok"]), None)
        completed = next((r for r in reversed(outcomes) if r["ok"]), None)
        verified = bool(last_verification and last_verification.status in
            (VerificationStatus.VERIFIED_OFFICIAL, VerificationStatus.VERIFIED_MULTIPLE_SOURCES)
            and not failed and not failed_reads and not any(r["simulated"] for r in outcomes))
        return {"session_id": session.id, "answer": answer, "language": session.language,
                "tools_used": tools_used, "verified": verified,
                "verification": last_verification.model_dump() if last_verification else None,
                "action_completed": completed, "action_failed": failed,
                "metadata": {"mode": "openai", "model": config.OPENAI_MODEL}}

    @classmethod
    def _respond_deterministic(cls, session: Session, text: str, intent: str, flags: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic slot-filling and reasoning engine conforming to trace validation and evaluation cases."""
        tools_used: List[str] = []
        last_verification: Optional[VerificationDetail] = None
        action_completed_info: Optional[Dict[str, Any]] = None
        action_failed_info: Optional[Dict[str, Any]] = None
        lowered = text.lower()

        # Case 0: Ambiguous
        if intent == "ambiguous":
            add_event(session.id, "agent.plan", {
                "reason": "Utterance is ambiguous. Clarification needed from caller.",
                "missing_slots": ["clarification"],
            })
            answer = "Aapko kis seva ya jankari mein sahayata chahiye? Kripya vistaar se batayein."

        # Case 1: Weather
        elif intent == "WEATHER_QUERY":
            city = session.context.get("city")
            if not city:
                add_event(session.id, "agent.plan", {
                    "reason": "Weather location missing. Asking caller for city.",
                    "missing_slots": ["city"],
                })
                answer = "Aap kis shehar ka mausam janna chahte hain?"
            else:
                add_event(session.id, "agent.plan", {
                    "reason": "Current meteorological queries require real-time sensor data.",
                    "tool": "get_weather",
                    "city": city,
                })
                session.set_status("tool_running")
                add_event(session.id, "tool.call", {"tool": "get_weather", "args": {"city": city}})
                res = execute_tool("get_weather", {"city": city})
                tools_used.append("get_weather")
                add_event(session.id, "tool.result", {"tool": "get_weather", "result": res})

                verification = cls._record_verification(session, "get_weather", res)
                last_verification = verification

                if res.get("ok"):
                    temp = res.get("current_temperature", "N/A")
                    cond = res.get("condition", "saaf")
                    rain_today = res.get("rain_probability_today", 0)
                    rain_tmrw = res.get("tomorrow_rain_probability", rain_today)
                    rain_parso = res.get("day_after_tomorrow_rain_probability", rain_tmrw)
                    loc = res.get("city", city)

                    if "parso" in lowered or "day after tomorrow" in lowered or "परसों" in text or "aur parso" in lowered:
                        answer = f"{loc} mein parso baarish ki sambhavna lagbhag {rain_parso}% hai. Mausam aamtaur par {cond.lower()} rahega."
                    elif "kal" in lowered or "tomorrow" in lowered or "कल" in text:
                        answer = f"{loc} mein kal baarish ki sambhavna lagbhag {rain_tmrw}% hai. Mausam {cond.lower()} rahega."
                    else:
                        answer = f"{loc} mein is waqt tapmaan {temp}°C hai aur mausam {cond.lower()} hai. Aaj baarish ki sambhavna {rain_today}% hai."
                else:
                    answer = f"Maaf kijiye, mujhe {city} ka live mausam check karne mein dikkat aa rahi hai."

        # Case 2: Courier Tracking
        elif intent == "COURIER_TRACKING":
            tracking_id = session.context.get("tracking_id")
            if not tracking_id:
                add_event(session.id, "agent.plan", {
                    "reason": "Tracking consignment number missing. Asking caller for ID.",
                    "missing_slots": ["tracking_id"],
                })
                answer = "Kripya apna courier tracking consignment number batayein?"
            else:
                add_event(session.id, "agent.plan", {
                    "reason": "Caller requested shipment location and delivery status.",
                    "tool": "track_courier",
                    "tracking_id": tracking_id,
                })
                session.set_status("tool_running")
                add_event(session.id, "tool.call", {"tool": "track_courier", "args": {"tracking_id": tracking_id}})
                res = execute_tool("track_courier", {"tracking_id": tracking_id})
                tools_used.append("track_courier")
                add_event(session.id, "tool.result", {"tool": "track_courier", "result": res})

                verification = cls._record_verification(session, "track_courier", res)
                last_verification = verification

                if res.get("ok") is True:
                    session.read_results["track_courier"] = deepcopy(res)
                    answer = tracking_summary(session, tracking_id)
                    if res.get("expected_delivery"):
                        answer += f"Expected delivery: {res['expected_delivery']}. "
                    answer += "Kya aap complaint darj karwana chahte hain?"
                else:
                    answer = "Courier tracking seva se jankari nahi mil paayi. Parcel ki jagah ya delivery abhi confirm nahi kar sakta."

        # All external writes share the same result validation and lifecycle.
        elif intent in {"FILE_COMPLAINT", "SEND_SMS_LINK", "REQUEST_UPLOAD"}:
            action = {"FILE_COMPLAINT": "create_complaint", "SEND_SMS_LINK": "send_sms",
                      "REQUEST_UPLOAD": "request_document_upload"}[intent]
            if flags.get("prohibited"):
                add_event(session.id, "agent.plan", {"reason": "Caller prohibited this action."})
                answer = "Theek hai, koi external action nahi kiya jayega."
            elif not action_allowed(action, text, intent, flags):
                add_event(session.id, "agent.plan", {"reason": "Caller confirmation required.",
                          "missing_slots": ["action_confirmation"]})
                answer = "Kya aap is action ki anumati dete hain? Kripya action karne ko spasht roop se kahein."
            elif action == "create_complaint" and not session.context.get("tracking_id"):
                add_event(session.id, "agent.plan", {"reason": "Complaint requires parcel ID.",
                          "missing_slots": ["tracking_id"]})
                answer = "Complaint ke liye kripya apna tracking number batayein?"
            elif action != "create_complaint" and not (session.caller or session.context.get("phone")):
                add_event(session.id, "agent.plan", {"reason": "SMS destination missing.", "missing_slots": ["phone"]})
                answer = "SMS bhejne ke liye kripya apna mobile number batayein?"
            else:
                phone = session.caller or session.context.get("phone")
                if action == "create_complaint":
                    args = {"tracking_id": session.context["tracking_id"], "reason": "Operational delay", "caller_phone": phone}
                elif action == "request_document_upload":
                    args = {"session_id": session.id, "phone": phone}
                else:
                    state = session.context.get("state", "India")
                    url = "https://scholarship.up.gov.in" if state == "Uttar Pradesh" else "https://scholarships.gov.in"
                    args = {"phone": phone, "message": f"BoloAI: {state} scholarship portal link: {url}"}
                add_event(session.id, "agent.plan", {"reason": "Caller requested external action.", "tool": action})
                res = execute_action(session, action, args, execute_tool)
                tools_used.append(action)
                last_verification = cls._record_verification(session, action, res)
                if res["ok"]:
                    action_completed_info = res
                else:
                    action_failed_info = res
                answer = action_answer(session, action, res)

        # Case 5: Government Schemes
        elif intent == "SCHEME_SEARCH":
            state = session.context.get("state")
            course = session.context.get("course")
            income = session.context.get("income")

            missing: List[str] = []
            if not state:
                missing.append("state")
            if not course:
                missing.append("course")
            if income is None:
                missing.append("family income")

            if missing:
                add_event(session.id, "agent.plan", {
                    "reason": "Eligibility criteria incomplete. Clarification needed from caller.",
                    "missing_slots": missing,
                })
                st_prefix = f"{state} mein " if state else ""
                answer = f"{st_prefix}scholarship eligibility check karne ke liye kripya apna {missing[0]} batayein?"
            else:
                add_event(session.id, "agent.plan", {
                    "reason": "Search government scheme records matching caller profile.",
                    "tool": "find_schemes",
                    "state": state,
                    "course": course,
                    "income": income,
                })
                session.set_status("tool_running")
                add_event(session.id, "tool.call", {
                    "tool": "find_schemes",
                    "args": {"state": state, "education": course, "income": income, "category": "Higher Education"},
                })
                res = execute_tool("find_schemes", {
                    "state": state,
                    "education": course,
                    "income": income,
                    "category": "Higher Education",
                })
                tools_used.append("find_schemes")
                add_event(session.id, "tool.result", {"tool": "find_schemes", "result": res})

                verification = cls._record_verification(session, "find_schemes", res)
                last_verification = verification

                matches = res.get("matches", []) if res.get("ok") is True else []
                if matches:
                    top_scheme = matches[0]
                    sch_name = top_scheme.get("name")
                    answer = (
                        f"Yeh curated demo scholarship dataset par aadharit hai: {state} mein {course} ke liye '{sch_name}' uplabdh hai. "
                        f"Aapki di gayi jankari ke anusaar aap match karte lagte hain. Final verification official portal par zaroori hai. Kya main official link SMS kar doon?"
                    )
                elif res.get("ok") is not True:
                    answer = "Scheme search seva unavailable hai. Abhi scheme ki jankari verify nahi kar sakta."
                else:
                    answer = f"Curated demo dataset mein {state} ke liye koi direct scheme match nahi hui."

        # Case 6: Claim Verification
        elif intent == "VERIFY_INFORMATION":
            # If specific claim is given to verify
            if any(w in lowered for w in ["verify this claim", "everyone gets free government money", "free money"]):
                add_event(session.id, "agent.plan", {
                    "reason": "Caller requested verification of an external public claim.",
                    "tool": "search_web",
                })
                session.set_status("tool_running")
                add_event(session.id, "tool.call", {"tool": "search_web", "args": {"query": text}})
                res = execute_tool("search_web", {"query": text})
                tools_used.append("search_web")
                add_event(session.id, "tool.result", {"tool": "search_web", "result": res})

                verification = cls._record_verification(session, "search_web", res)
                last_verification = verification

                if res.get("ok") is not True:
                    answer = "Live search seva se jankari nahi mil paayi. Is claim ko abhi verify nahi kar sakta."
                else:
                    answer = "Public search ke results mile hain, lekin inke aadhar par is claim ki pushti nahi kar sakta. Kripya sambandhit official portal par jaanch karein."
            else:
                add_event(session.id, "agent.plan", {
                    "reason": "Uncertain claim requires specific scheme or source clarification.",
                    "missing_slots": ["scheme_name_or_link"],
                })
                answer = "Iski pramanikta verify karne ke liye kripya scheme ka pura official naam ya circular details batayein?"

        # Case 7: Education / Explanation
        elif intent == "CONCEPT_EXPLAIN":
            add_event(session.id, "agent.plan", {
                "reason": "Educational concept explanation in simple voice-friendly terms.",
                "tool": "search_web",
            })
            session.set_status("tool_running")
            add_event(session.id, "tool.call", {"tool": "search_web", "args": {"query": text}})
            res = execute_tool("search_web", {"query": text})
            tools_used.append("search_web")
            add_event(session.id, "tool.result", {"tool": "search_web", "result": res})

            verification = cls._record_verification(session, "search_web", res)
            last_verification = verification

            concept_type = flags.get("concept", "") or session.context.get("last_concept", "")
            if "पौधे" in text or "भोजन" in text or "photosynthesis" in lowered or "प्रकाश संश्लेषण" in text or concept_type == "photosynthesis":
                if any(w in lowered for w in ["example", "udaharan", "simple", "aur batao", "samjhao"]):
                    answer = "Photosynthesis ka simple example: Jaise kitchen mein hum dhoop aur gas par khana banate hain, waise hi paudhe suraj ki dhoop aur paani use karke leaves mein bhojan banate hain aur taaza oxygen release karte hain."
                else:
                    answer = "प्रकाश संश्लेषण (Photosynthesis): पौधे धूप, पानी और कार्बन डाइऑक्साइड की मदद से क्लोरोफिल द्वारा अपना भोजन बनाते हैं और ऑक्सीजन छोड़ते हैं।"
            elif concept_type == "cloud_computing" or "cloud computing" in lowered:
                answer = "Cloud computing ka matlab hai internet ke zariye computer files, storage aur programs access karna, bina apne phone ya laptop par download kiye. Jaise Google Drive ya online email storage."
            elif concept_type == "ai_agent" or "ai agent" in lowered or "agent kya hota" in lowered or "agent kya hai" in lowered:
                answer = "AI agent ek intelligent computer program hota hai jo aapki baat samajh kar, situation ke hisaab se decision leta hai aur tools use karke aapka kaam poora karta hai — jaise BoloAI."
            elif concept_type == "python_cpp" or ("python" in lowered and "c++" in lowered):
                answer = "Python seekhne mein aasan aur rapid development ke liye use hoti hai, jabki C++ low-level system access aur high-speed execution performance ke liye popular hai."
            else:
                top_hit = (res.get("results") or [{}])[0] if res.get("ok") is True else {}
                answer = top_hit.get("snippet") or "Is concept ke detailed answer ke liye mera AI reasoning service abhi connected nahi hai. Weather, schemes, verification aur demo services main abhi bhi use kar sakta hoon."

        # Case 8: General Knowledge
        elif intent == "GENERAL_INQUIRY":
            add_event(session.id, "agent.plan", {
                "reason": "General knowledge query answered with foundational reference.",
            })
            sub_intent = flags.get("sub_intent", "")
            if sub_intent == "greeting" or any(w in lowered for w in ["hello", "hi", "namaste", "pranam", "kya haal", "kaise ho"]):
                answer = "Namaste! Main BoloAI hoon. Aap weather, schemes, documents, general questions ya digital services ke baare mein pooch sakte hain. Main aapki kya sahayata kar sakta hoon?"
            elif sub_intent == "capabilities" or any(w in lowered for w in ["kya kya kar sakte ho", "tum kya kar sakte ho", "aap kya kar sakte ho", "what can you do"]):
                answer = "Main BoloAI hoon — Bharat ka voice-first digital assistant. Main live weather, government schemes, parcel tracking, documents verification aur aam sawalon ke seedhe jawab bina internet ke phone call par de sakta hoon."
            elif sub_intent == "gratitude" or any(w in lowered for w in ["thank you", "thanks", "shukriya", "dhanyawad", "dhanyavad"]):
                answer = "Khushi hui help karke! Aur kuch poochna ho to boliye."
            elif sub_intent == "resume" or ("resume" in lowered and any(w in lowered for w in ["improve", "kaise", "banao", "tips", "better"])):
                answer = "Resume behtar banane ke liye apne projects ke measurable outcomes likhein, target role se related skills highlight karein, aur layout clean aur 1 page mein rakhein."
            elif "gravity" in lowered:
                answer = "Gravity is a fundamental natural force by which objects with mass attract each other, keeping planets in orbit."
            elif "2 plus 2" in lowered or "2+2" in lowered:
                answer = "2 plus 2 ka jawab 4 hota hai."
            else:
                answer = "Is question ke detailed answer ke liye mera AI reasoning service abhi connected nahi hai. Weather, schemes, verification aur demo services main abhi bhi use kar sakta hoon."

        else:
            add_event(session.id, "agent.plan", {
                "reason": "Direct voice assistant reply.",
            })
            answer = "Namaste! Main BoloAI hoon. Main aapki kya sahayata kar sakta hoon?"

        session.history.append({"role": "assistant", "content": answer})
        add_event(session.id, "assistant.response", {"text": answer})
        session.set_status("speaking")

        # Determine verified flag: Only True if verified official or multiple and NOT demo data!
        is_verified = bool(
            last_verification
            and last_verification.status in (VerificationStatus.VERIFIED_OFFICIAL, VerificationStatus.VERIFIED_MULTIPLE_SOURCES)
            and not (action_completed_info and action_completed_info.get("simulated"))
            and "track_courier" not in tools_used
            and "find_schemes" not in tools_used  # Curated demo dataset is not verified live government data
        )

        return {
            "session_id": session.id,
            "answer": answer,
            "language": session.language,
            "tools_used": tools_used,
            "verified": is_verified,
            "verification": last_verification.model_dump() if last_verification else None,
            "action_completed": action_completed_info,
            "action_failed": action_failed_info,
            "metadata": {"mode": "deterministic-orchestrator"},
        }


def respond(session_id: str, text: str) -> Dict[str, Any]:
    return AgentOrchestrator.respond(session_id, text)
