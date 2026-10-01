"""Run with: python -m uvicorn mock_services.main:app --port 9001.

All timestamps are fixture time, not current observations. No providers are called.
Complaint retries are idempotent by tracking ID and reason; SMS IDs are sequential
within this process. State resets when the server restarts.
"""
from hashlib import sha256
from threading import Lock

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

FIXTURE_TIME = "2026-10-01T09:00:00+05:30"
NOTICE = "Fictional demonstration only; no official eligibility or provider action."
SCHEMES = [
    {"id": "DEMO-UP-ENGINEERING", "name": "Fictional UP Engineering Study Grant",
     "state": "Uttar Pradesh", "course": "BTech", "max_income": 250000,
     "benefit": "Illustrative annual study support of INR 12000",
     "authority": "Fictional Demo Education Office", "official_url": None,
     "eligibility": "Demo residents studying BTech; annual family income <= INR 250000",
     "source_type": "DEMO_DATA", "demo": True},
    {"id": "DEMO-ALL-DIPLOMA", "name": "Fictional Diploma Learning Grant",
     "state": "All-India", "course": "Diploma", "max_income": 200000,
     "benefit": "Illustrative annual study support of INR 8000",
     "authority": "Fictional Demo Education Office", "official_url": None,
     "eligibility": "Demo diploma students; annual family income <= INR 200000",
     "source_type": "DEMO_DATA", "demo": True},
]


class Complaint(BaseModel):
    reason: str = Field(default="Operational delay", min_length=1, max_length=1000)


class SMS(BaseModel):
    phone: str = Field(pattern=r"^\+?[1-9]\d{9,14}$")
    message: str = Field(min_length=1, max_length=1600)


def courier(tracking_id: str) -> dict:
    tracking_id = tracking_id.strip().upper()
    if tracking_id != "ABC123":
        raise HTTPException(404, "No demo parcel with this tracking ID")
    return {"ok": True, "demo": True, "simulated": True, "tracking_id": tracking_id,
            "status": "delayed", "current_hub": "Ghaziabad Hub",
            "current_location": "Ghaziabad Hub", "reason": "operational delay",
            "expected_delivery": "2026-10-02T18:00:00+05:30",
            "last_update": FIXTURE_TIME, "notice": NOTICE}


def complaint(tracking_id: str, reason: str = "Operational delay") -> dict:
    courier(tracking_id)
    token = sha256((tracking_id.upper() + ":" + reason).encode()).hexdigest()[:12].upper()
    return {"ok": True, "success": True, "demo": True, "simulated": True,
            "action_type": "REGISTER_COMPLAINT", "reference_id": f"DEMO-CMP-{token}",
            "tracking_id": tracking_id.upper(), "reason": reason,
            "status": "SIMULATED_REGISTERED", "timestamp": FIXTURE_TIME, "notice": NOTICE}


def schemes(state: str | None = None, course: str | None = None,
            income: float | None = None) -> dict:
    normalized = "Uttar Pradesh" if (state or "").lower() == "up" else state
    matches = [dict(item) for item in SCHEMES
               if (not normalized or item["state"].lower() in (normalized.lower(), "all-india"))
               and (not course or item["course"].lower() == course.lower())
               and (income is None or income <= item["max_income"])]
    return {"ok": True, "demo": True, "verified": False, "matches": matches, "notice": NOTICE}


def create_app() -> FastAPI:
    service = FastAPI(title="BoloAI fictional demo services")
    messages: list[dict] = []
    lock = Lock()

    @service.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"demo": True, "error": exc.detail})

    @service.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"demo": True, "error": "Invalid demo input"})

    @service.get("/health")
    def health():
        return {"ok": True, "demo": True, "service": "boloai-mock-services", "notice": NOTICE}

    @service.get("/courier/{tracking_id}")
    def get_courier(tracking_id: str):
        return courier(tracking_id)

    @service.post("/courier/{tracking_id}/complaint")
    def create_complaint(tracking_id: str, body: Complaint = Complaint()):
        return complaint(tracking_id, body.reason)

    @service.get("/schemes")
    def get_schemes(state: str | None = None, course: str | None = None,
                    income: float | None = Query(default=None, ge=0)):
        return schemes(state, course, income)

    @service.post("/sms")
    def send_sms(body: SMS):
        with lock:
            item = {**body.model_dump(), "ok": True, "success": True, "demo": True,
                    "simulated": True, "reference_id": f"DEMO-SMS-{len(messages) + 1:06d}",
                    "status": "SIMULATED_SENT", "timestamp": FIXTURE_TIME, "notice": NOTICE}
            messages.append(item)
            return dict(item)

    @service.get("/sms")
    def get_sms():
        with lock:
            return {"demo": True, "messages": [dict(item) for item in messages], "notice": NOTICE}

    return service


app = create_app()
