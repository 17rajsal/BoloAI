from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
from typing import Any, Dict, Optional

UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class UploadToken:
    token: str
    session_id: str
    caller: Optional[str]
    expires_at: datetime
    status: str = "PENDING"  # PENDING, UPLOADED, EXPIRED, FAILED
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size_bytes: int = 0
    created_at: datetime = field(default_factory=now_utc)

    def is_expired(self) -> bool:
        return now_utc() > self.expires_at


class UploadTokenService:
    """Manages secure, short-lived tokens for mobile document/photo upload without exposing session IDs."""

    _tokens: Dict[str, UploadToken] = {}

    @classmethod
    def create_token(cls, session_id: str, caller: Optional[str] = None, valid_minutes: int = 15) -> UploadToken:
        token_str = secrets.token_urlsafe(12)  # e.g. "aX8_9Q2Lm..."
        expires = now_utc() + timedelta(minutes=valid_minutes)
        tok = UploadToken(
            token=token_str,
            session_id=session_id,
            caller=caller,
            expires_at=expires,
        )
        cls._tokens[token_str] = tok
        return tok

    @classmethod
    def get_token(cls, token_str: str) -> Optional[UploadToken]:
        tok = cls._tokens.get(token_str)
        if not tok:
            return None
        if tok.is_expired():
            tok.status = "EXPIRED"
            return None
        return tok

    @classmethod
    def record_upload(cls, token_str: str, file_path: str, file_name: str, mime_type: str, file_size: int) -> UploadToken:
        tok = cls._tokens[token_str]
        tok.status = "UPLOADED"
        tok.file_path = file_path
        tok.file_name = file_name
        tok.mime_type = mime_type
        tok.file_size_bytes = file_size
        return tok
