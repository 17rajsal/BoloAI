from typing import Any, Callable, Dict, List, Optional
from .weather import get_weather
from .search import search_web
from .schemes import find_schemes
from .courier import track_courier, create_complaint
from .sms import send_sms
from ..services.actions import normalize_action_result


# Backward compatibility wrapper for find_demo_schemes
def find_demo_schemes(state: Optional[str] = None, course: Optional[str] = None, max_family_income: Optional[float] = None) -> Dict[str, Any]:
    return find_schemes(state=state, education=course, income=max_family_income, include_demo=True)


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get live weather and forecast for any Indian city or location. Use for queries about weather, rain, temperature, or climate.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City or town name, e.g. 'Delhi', 'Jaipur', 'Lucknow'"}
            },
            "required": ["city"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_web",
        "description": "Search the live web for fresh, current information, facts, news, or general public queries where fresh information is needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword or question to research"}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "find_schemes",
        "description": "Search verified government schemes and scholarships based on caller's state, education, and family income.",
        "parameters": {
            "type": "object",
            "properties": {
                "state": {"type": ["string", "null"], "description": "State of residence (e.g., 'Uttar Pradesh', 'Bihar', 'Rajasthan')"},
                "education": {"type": ["string", "null"], "description": "Degree or level of study (e.g., 'BTech', '12th', 'Diploma')"},
                "income": {"type": ["number", "null"], "description": "Annual family income in Rupees, e.g. 200000"},
                "category": {"type": ["string", "null"], "description": "Category or interest area, e.g., 'Higher Education', 'Agriculture'"},
            },
            "required": ["state", "education", "income", "category"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "track_courier",
        "description": "Track the live status, location, and estimated delivery time of a courier package or parcel.",
        "parameters": {
            "type": "object",
            "properties": {
                "tracking_id": {"type": "string", "description": "Tracking consignment number, e.g., 'ABC123'"}
            },
            "required": ["tracking_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "create_complaint",
        "description": "File an official grievance or complaint regarding a delayed courier package. Generates a reference ticket ID. Only invoke when user requests or confirms filing a complaint.",
        "parameters": {
            "type": "object",
            "properties": {
                "tracking_id": {"type": "string", "description": "The parcel tracking ID to lodge complaint against"},
                "reason": {"type": "string", "description": "Brief explanation of the delay or issue"},
                "caller_phone": {"type": ["string", "null"], "description": "Contact phone number for updates"},
            },
            "required": ["tracking_id", "reason", "caller_phone"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "send_sms",
        "description": "Send an SMS with official link, status, or details to the caller's phone number. Only invoke when user explicitly requests SMS delivery.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Caller mobile number to deliver SMS"},
                "message": {"type": "string", "description": "Concise text message containing details or official portal link"},
            },
            "required": ["phone", "message"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "request_document_upload",
        "description": "Send an SMS link to the caller allowing them to upload a photo, poster, or document for verification.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID"},
                "phone": {"type": ["string", "null"], "description": "Caller mobile number"},
            },
            "required": ["session_id", "phone"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def request_document_upload(session_id: str, phone: Optional[str] = None) -> Dict[str, Any]:
    from ..services.upload import UploadTokenService
    from .. import config
    from .sms import send_sms

    tok = UploadTokenService.create_token(session_id=session_id, caller=phone)
    base_url = config.PUBLIC_WS_BASE.replace("ws://", "http://").replace("wss://", "https://").rstrip("/")
    upload_url = f"{base_url}/u/{tok.token}"
    msg = f"BoloAI: Kripya is link par photo upload karein: {upload_url}"
    sms_res = normalize_action_result("send_sms", send_sms(phone, msg))
    if not sms_res["ok"]:
        tok.status = "FAILED"
        return {"ok": False, "simulated": sms_res["simulated"],
                "reference_id": None, "error": sms_res["error"], "sms_dispatched": False}
    return {
        "ok": sms_res["ok"],
        "simulated": sms_res["simulated"],
        "action": "request_document_upload",
        "token": tok.token,
        "upload_url": upload_url,
        "sms_dispatched": sms_res["ok"],
        "reference_id": sms_res.get("reference_id"),
        "message": "Demo upload-link SMS simulated." if sms_res["simulated"] else "SMS provider accepted the upload-link request.",
    }


TOOL_METADATA = {
    "get_weather": {
        "title": "Live Weather",
        "icon": "cloud-sun",
        "badge": "Live Meteorological Data",
        "is_action": False,
    },
    "search_web": {
        "title": "Web Search",
        "icon": "globe",
        "badge": "Current Web Search",
        "is_action": False,
    },
    "find_schemes": {
        "title": "Government Schemes",
        "icon": "landmark",
        "badge": "Curated Verified Dataset",
        "is_action": False,
    },
    "find_demo_schemes": {
        "title": "Demo Scheme Search",
        "icon": "landmark",
        "badge": "Demo / Mock",
        "is_action": False,
    },
    "track_courier": {
        "title": "Courier Tracking",
        "icon": "truck",
        "badge": "Logistics Status (Simulated)",
        "is_action": False,
    },
    "create_complaint": {
        "title": "Register Complaint",
        "icon": "alert-circle",
        "badge": "Executive Action",
        "is_action": True,
    },
    "send_sms": {
        "title": "Send SMS",
        "icon": "message-square",
        "badge": "Outbound Dispatch",
        "is_action": True,
    },
    "request_document_upload": {
        "title": "Document Upload Handoff",
        "icon": "camera",
        "badge": "Multimodal Handoff",
        "is_action": True,
    },
}


class ToolRegistry:
    """Central registry and executor for all BoloAI tools."""

    _handlers: Dict[str, Callable] = {
        "get_weather": get_weather,
        "search_web": search_web,
        "find_schemes": find_schemes,
        "find_demo_schemes": find_demo_schemes,
        "track_courier": track_courier,
        "create_complaint": create_complaint,
        "send_sms": send_sms,
        "request_document_upload": request_document_upload,
    }

    @classmethod
    def execute(cls, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        handler = cls._handlers.get(name)
        if not handler:
            return {"ok": False, "error": f"Tool '{name}' is not registered."}
        try:
            result = handler(**args)
            if cls.get_metadata(name).get("is_action"):
                return normalize_action_result(name, result)
            if not isinstance(result, dict):
                return {"ok": False, "error": "Tool returned an invalid result"}
            return result
        except Exception as exc:
            return {"ok": False, "error": f"Tool execution failed: {str(exc)}"}

    @classmethod
    def get_schemas(cls) -> List[Dict[str, Any]]:
        return TOOL_SCHEMAS

    @classmethod
    def get_metadata(cls, name: str) -> Dict[str, Any]:
        return TOOL_METADATA.get(name, {
            "title": name.replace("_", " ").title(),
            "icon": "tool",
            "badge": "Tool",
            "is_action": False,
        })


def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return ToolRegistry.execute(name, args)
