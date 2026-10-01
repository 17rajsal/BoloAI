import pytest

from evals.sandbox import new_session, turn


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["ok"] is True


def test_session_creation_unique_ids(client):
    first, second = new_session(client), new_session(client)
    assert first != second
    assert client.get(f"/sessions/{first}").json()["session_id"] == first


def test_conversation_context_survives_later_turn(client):
    sid = new_session(client)
    turn(client, sid, "I live in Uttar Pradesh.")
    turn(client, sid, "Mere state ki schemes batao.")
    details = client.get(f"/sessions/{sid}").json()
    assert details["context"]["state"] == "Uttar Pradesh"
    assert len(details["history"]) == 4
    events = client.get(f"/sessions/{sid}/events").json()["events"]
    missing = [e["data"].get("missing_slots", []) for e in events if e["type"] == "agent.plan"]
    assert not any("state" in slot for group in missing for slot in group)


@pytest.mark.parametrize("demo_mode", [True, False])
def test_agent_without_openai_key(client, monkeypatch, demo_mode):
    from app import config
    monkeypatch.setattr(config, "DEMO_MODE", demo_mode)
    assert not config.OPENAI_API_KEY
    output = turn(client, new_session(client), "Namaste")
    assert output["answer"]
    assert output["metadata"]["mode"] == "deterministic-orchestrator"


def test_empty_turn_rejected(client):
    response = client.post("/agent/respond", json={"session_id": new_session(client), "text": ""})
    assert response.status_code == 422


def test_weather_dispatch_and_unavailable_provider(client):
    sid = new_session(client)
    output = turn(client, sid, "Delhi ka weather kya hai?")
    assert "get_weather" in output["tools_used"]
    assert output["verified"] is False
    assert output["verification"]["status"] == "UNVERIFIED"
    events = client.get(f"/sessions/{sid}/events").json()["events"]
    assert any(e["type"] == "tool.call" and e["data"]["tool"] == "get_weather" for e in events)


@pytest.mark.parametrize("args", [{}, {"wrong_field": "Delhi"}, None, [], {"city": None, "extra": 1}])
def test_malformed_tool_input_safe(client, args):
    from app.tools.registry import ToolRegistry
    # Use the real handler signature; malformed inputs must fail before networking.
    from app.tools.weather import get_weather
    ToolRegistry._handlers["get_weather"] = get_weather
    result = ToolRegistry.execute("get_weather", args)
    assert result["ok"] is False
    assert result.get("error")


def test_unknown_tool_rejected(client):
    from app.tools.registry import ToolRegistry
    assert ToolRegistry.execute("not_a_tool", {})["ok"] is False


def test_courier_reference_captured_in_events(client):
    sid = new_session(client)
    assert "track_courier" in turn(client, sid, "Mera parcel ABC123 kaha hai?")["tools_used"]
    output = turn(client, sid, "Complaint register kar do.")
    ref = output["action_completed"]["reference_id"]
    assert ref.startswith("DEMO-CMP-")
    events = client.get(f"/sessions/{sid}/events").json()["events"]
    assert any(e["type"] == "action.completed" and e["data"].get("reference_id") == ref for e in events)
