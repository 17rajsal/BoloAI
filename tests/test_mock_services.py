import pytest
from fastapi.testclient import TestClient

from mock_services.main import create_app


@pytest.fixture
def mock_client():
    with TestClient(create_app()) as client:
        yield client


def test_mock_health(mock_client):
    assert mock_client.get("/health").json()["service"] == "boloai-mock-services"


def test_courier_deterministic(mock_client):
    one = mock_client.get("/courier/ABC123").json()
    assert one == mock_client.get("/courier/ABC123").json()
    assert one["demo"] and one["status"] == "delayed"
    assert one["current_hub"] == "Ghaziabad Hub"
    assert one["reason"] == "operational delay"
    assert one["expected_delivery"] and one["last_update"]
    first = mock_client.post("/courier/ABC123/complaint", json={"reason": "Delayed"}).json()
    assert first == mock_client.post("/courier/ABC123/complaint", json={"reason": "Delayed"}).json()
    assert first["success"] and first["reference_id"].startswith("DEMO-CMP-")


def test_scheme_filters_and_label(mock_client):
    response = mock_client.get("/schemes", params={"state": "UP", "course": "BTech", "income": 180000}).json()
    assert response["demo"] and response["verified"] is False
    assert len(response["matches"]) == 1
    assert all(m["demo"] and m["source_type"] == "DEMO_DATA" and m["official_url"] is None for m in response["matches"])
    for params in ({"income": 999999}, {"state": "Kerala", "course": "BTech"}, {"course": "MBBS"}):
        assert mock_client.get("/schemes", params=params).json()["matches"] == []


def test_sms_in_memory(mock_client):
    assert mock_client.get("/sms").json()["messages"] == []
    payload = {"phone": "+919000000001", "message": "Fictional demo message"}
    first = mock_client.post("/sms", json=payload).json()
    second = mock_client.post("/sms", json=payload).json()
    assert first["success"] and first["demo"] and first["simulated"]
    assert first["reference_id"] == "DEMO-SMS-000001"
    assert second["reference_id"] == "DEMO-SMS-000002"
    assert mock_client.get("/sms").json()["messages"] == [first, second]
    with TestClient(create_app()) as fresh:
        assert fresh.get("/sms").json()["messages"] == []


@pytest.mark.parametrize("method,path,payload,status", [
    ("get", "/courier/UNKNOWN", None, 404),
    ("post", "/courier/UNKNOWN/complaint", {}, 404),
    ("post", "/sms", {"phone": "bad", "message": "demo"}, 422),
    ("post", "/sms", {"phone": "+919000000001", "message": ""}, 422),
    ("get", "/schemes?income=-1", None, 422),
    ("get", "/missing", None, 404),
])
def test_errors_also_labeled_demo(mock_client, method, path, payload, status):
    response = mock_client.request(method, path, json=payload)
    assert response.status_code == status
    assert response.json()["demo"] is True
