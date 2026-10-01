from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from threading import RLock


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Session:
    id: str
    caller: Optional[str] = None
    language: str = "auto"
    history: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    current_goal: Optional[str] = None
    tools_used: List[str] = field(default_factory=list)
    verification_results: List[Dict[str, Any]] = field(default_factory=list)
    actions_requested: List[Dict[str, Any]] = field(default_factory=list)
    actions_confirmed: List[Dict[str, Any]] = field(default_factory=list)
    actions_completed: List[Dict[str, Any]] = field(default_factory=list)
    actions_failed: List[Dict[str, Any]] = field(default_factory=list)
    action_executions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    turn_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    turn_inputs: Dict[str, str] = field(default_factory=dict)
    active_turn_id: str = ""
    read_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    turn_lock: Any = field(default_factory=RLock, repr=False, compare=False)
    call_status: str = "idle"  # idle, listening, thinking, tool_running, speaking, ended
    stream_sid: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def update_context(self, new_context: Dict[str, Any]) -> None:
        for k, v in new_context.items():
            if v is not None:
                self.context[k] = v
        self.updated_at = now_iso()

    def set_goal(self, goal: str) -> None:
        self.current_goal = goal
        self.updated_at = now_iso()

    def set_status(self, status: str) -> None:
        self.call_status = status
        self.updated_at = now_iso()


class BaseSessionStore(ABC):
    @abstractmethod
    def create(self, caller: Optional[str] = None, language: str = "auto", session_id: Optional[str] = None) -> Session:
        pass

    @abstractmethod
    def get(self, session_id: str) -> Optional[Session]:
        pass

    @abstractmethod
    def ensure(self, session_id: str, caller: Optional[str] = None) -> Session:
        pass

    @abstractmethod
    def add_event(self, session_id: str, event_type: str, data: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def list_all(self, limit: int = 50) -> List[Session]:
        pass


class InMemorySessionStore(BaseSessionStore):
    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create(self, caller: Optional[str] = None, language: str = "auto", session_id: Optional[str] = None) -> Session:
        sid = session_id or f"bolo-{uuid4().hex[:8]}"
        session = Session(id=sid, caller=caller, language=language)
        self._sessions[sid] = session
        self.add_event(sid, "session.created", {"caller": caller, "language": language})
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def ensure(self, session_id: str, caller: Optional[str] = None) -> Session:
        if session_id in self._sessions:
            if caller and not self._sessions[session_id].caller:
                self._sessions[session_id].caller = caller
            return self._sessions[session_id]
        return self.create(caller=caller, session_id=session_id)

    def add_event(self, session_id: str, event_type: str, data: Dict[str, Any]) -> None:
        if session_id in self._sessions:
            s = self._sessions[session_id]
            evt = {"ts": now_iso(), "type": event_type, "data": data}
            s.events.append(evt)
            s.updated_at = now_iso()

    def list_all(self, limit: int = 50) -> List[Session]:
        return sorted(list(self._sessions.values()), key=lambda s: s.updated_at, reverse=True)[:limit]


# Global SessionManager instance
session_store: BaseSessionStore = InMemorySessionStore()

# Convenience backward-compatible functions
def create_session(caller=None, language="auto", session_id=None) -> Session:
    return session_store.create(caller=caller, language=language, session_id=session_id)


def get_session(session_id: str) -> Session:
    s = session_store.get(session_id)
    if not s:
        raise KeyError(session_id)
    return s


def ensure_session(session_id: str, caller=None) -> Session:
    return session_store.ensure(session_id, caller=caller)


def add_event(session_id: str, event_type: str, data: Dict[str, Any]) -> None:
    session_store.add_event(session_id, event_type, data)


def get_all_sessions(limit: int = 50) -> List[Session]:
    return session_store.list_all(limit=limit)
