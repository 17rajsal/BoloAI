from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, Optional

# In-memory action idempotency cache: {action_hash: (result_dict, timestamp)}
_ACTION_CACHE: Dict[str, Dict[str, Any]] = {}


def generate_action_key(session_id: str, action_name: str, payload_str: str, turn_id: str = "") -> str:
    raw = f"{session_id}:{action_name}:{payload_str}:{turn_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_cached_action(action_key: str) -> Optional[Dict[str, Any]]:
    return _ACTION_CACHE.get(action_key)


def record_action_execution(action_key: str, result: Dict[str, Any]) -> None:
    _ACTION_CACHE[action_key] = result
