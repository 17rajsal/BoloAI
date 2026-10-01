from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VerificationStatus(str, Enum):
    VERIFIED_OFFICIAL = "VERIFIED_OFFICIAL"
    VERIFIED_MULTIPLE_SOURCES = "VERIFIED_MULTIPLE_SOURCES"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    CONFLICTING = "CONFLICTING"
    UNVERIFIED = "UNVERIFIED"


class SourceType(str, Enum):
    VERIFIED_OFFICIAL = "VERIFIED_OFFICIAL"
    DEMO_DATA = "DEMO_DATA"
    UNVERIFIED = "UNVERIFIED"


class SchemeItem(BaseModel):
    name: str
    authority: str
    state: str = "All-India"
    category: str = "General"
    eligibility: str
    income_criteria: Optional[float] = None
    benefit: str
    application_process: str
    required_documents: List[str] = Field(default_factory=list)
    official_url: Optional[str] = None
    last_verified_date: str
    source_type: SourceType = SourceType.VERIFIED_OFFICIAL


class VerificationDetail(BaseModel):
    status: VerificationStatus
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    reason: str
    timestamp: str = Field(default_factory=now_iso)
    confidence_label: str = "High"


class CreateSessionRequest(BaseModel):
    caller: Optional[str] = None
    language: str = "auto"


class AgentRequest(BaseModel):
    session_id: str
    text: str = Field(min_length=1)
    audio_base64: Optional[str] = None
    turn_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


class AgentResponse(BaseModel):
    session_id: str
    answer: str
    language: str = "hi-IN"
    tools_used: List[str] = Field(default_factory=list)
    verified: bool = False
    verification: Optional[VerificationDetail] = None
    action_completed: Optional[Dict[str, Any]] = None
    action_failed: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionEvent(BaseModel):
    ts: str = Field(default_factory=now_iso)
    type: str
    data: Dict[str, Any] = Field(default_factory=dict)


class HealthStatus(BaseModel):
    ok: bool
    service: str = "BoloAI"
    version: str = "1.0.0"
    mode: str
    providers: Dict[str, Dict[str, Any]]
