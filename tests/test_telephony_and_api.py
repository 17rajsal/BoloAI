import base64
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.adapters.telephony import TelephonyAdapter
from app.adapters.stt import pcm_to_wav
from app.adapters.tts import generate_mock_pcm_audio

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["service"] == "BoloAI"
    assert "providers" in data
    assert "openai" in data["providers"]
    assert "sarvam_stt" in data["providers"]
    assert "sarvam_tts" in data["providers"]
    assert "exotel" in data["providers"]


def test_session_endpoints():
    create_resp = client.post("/sessions", json={"caller": "+919876543210", "language": "hi-IN"})
    assert create_resp.status_code == 200
    s_data = create_resp.json()
    sid = s_data["session_id"]
    assert sid.startswith("bolo-")

    list_resp = client.get("/sessions")
    assert list_resp.status_code == 200
    s_list = list_resp.json()
    assert any(s["session_id"] == sid for s in s_list)


def test_agent_respond_endpoint():
    s_resp = client.post("/sessions", json={"language": "hi-IN"})
    sid = s_resp.json()["session_id"]

    resp = client.post("/agent/respond", json={"session_id": sid, "text": "Jaipur mein mausam kaisa hai?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert len(data["answer"]) > 5
    assert "get_weather" in data["tools_used"]


def test_agent_voice_turn_endpoint():
    s_resp = client.post("/sessions", json={"language": "hi-IN"})
    sid = s_resp.json()["session_id"]

    mock_audio = generate_mock_pcm_audio(duration_sec=0.5, sample_rate=8000)
    audio_b64 = base64.b64encode(mock_audio).decode("ascii")

    resp = client.post("/agent/voice-turn", json={
        "session_id": sid,
        "text": "Delhi weather",
        "audio_base64": audio_b64,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "audio_response_base64" in data
    assert data["audio_sample_rate"] == 8000


def test_exotel_resolve_endpoint():
    resp = client.get("/exotel/resolve?CallSid=call-exotel-999&CallFrom=%2B919876543210")
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "/ws/exotel/call-exotel-999" in data["url"]


def test_telephony_adapter_helpers():
    pcm_audio = generate_mock_pcm_audio(duration_sec=0.1, sample_rate=8000)
    wav_bytes = pcm_to_wav(pcm_audio, sample_rate=8000)
    assert wav_bytes.startswith(b"RIFF")

    raw_event = '{"event": "start", "start": {"stream_sid": "str-123"}}'
    parsed = TelephonyAdapter.parse_event(raw_event)
    assert parsed["event"] == "start"
    assert parsed["start"]["stream_sid"] == "str-123"

    payload_b64 = base64.b64encode(b"test-audio-bytes").decode("ascii")
    decoded = TelephonyAdapter.decode_media_payload({"payload": payload_b64})
    assert decoded == b"test-audio-bytes"
