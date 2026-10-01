"""Offline provider boundary, leaving orchestration and verification under test.

No .env edits, real credentials, provider calls or global state survive this scope.
Weather deliberately fails: routing still must occur, and model memory must not
be presented as a verified current forecast. This is not a live-provider test.
"""
from contextlib import ExitStack, contextmanager
import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

from mock_services.main import complaint, courier, create_app, schemes


@contextmanager
def isolated_app():
    from app import config, store
    from app.main import app
    from app.tools.registry import ToolRegistry

    with ExitStack() as stack:
        previous_logging = logging.root.manager.disable
        logging.disable(logging.WARNING)
        stack.callback(logging.disable, previous_logging)
        for key, value in {"DEMO_MODE": True, "OPENAI_API_KEY": "", "SMS_PROVIDER": "mock",
                           "EXOTEL_API_KEY": "", "EXOTEL_API_TOKEN": "",
                           "EXOTEL_ACCOUNT_SID": "", "SARVAM_API_KEY": ""}.items():
            stack.enter_context(patch.object(config, key, value))
        stack.enter_context(patch.object(store, "session_store", store.InMemorySessionStore()))
        mock = stack.enter_context(TestClient(create_app()))
        handlers = dict(ToolRegistry._handlers)
        handlers.update({
            "get_weather": lambda **kwargs: {"ok": False, "error": "Offline evaluation: live provider unavailable"},
            "search_web": lambda **kwargs: {"ok": False, "results": [], "error": "Offline evaluation"},
            "find_schemes": lambda state=None, education=None, income=None, **kwargs: schemes(state, education, income),
            "find_demo_schemes": lambda state=None, course=None, max_family_income=None: schemes(state, course, max_family_income),
            "track_courier": courier,
            "create_complaint": lambda tracking_id, reason="Operational delay", caller_phone=None: complaint(tracking_id, reason),
            "send_sms": lambda phone, message: mock.post("/sms", json={"phone": phone, "message": message}).json(),
        })
        stack.enter_context(patch.object(ToolRegistry, "_handlers", handlers))
        # Catch accidental outbound HTTP, even if future core changes bypass handlers.
        stack.enter_context(patch("httpx.HTTPTransport.handle_request", side_effect=RuntimeError("Network disabled in evaluation")))
        stack.enter_context(patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=RuntimeError("Network disabled in evaluation")))
        yield stack.enter_context(TestClient(app))


def new_session(client) -> str:
    response = client.post("/sessions", json={"caller": "+919000000001", "language": "hi-IN"})
    response.raise_for_status()
    return response.json()["session_id"]


def turn(client, session_id: str, message: str) -> dict:
    response = client.post("/agent/respond", json={"session_id": session_id, "text": message})
    response.raise_for_status()
    return response.json()
