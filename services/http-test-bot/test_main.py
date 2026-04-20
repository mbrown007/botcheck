from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_health_reports_scripted_mode() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "scripted"}


def test_chat_returns_scripted_billing_reply() -> None:
    response = client.post(
        "/chat",
        json={
            "message": "Hi, I need help with billing.",
            "history": [],
            "session_id": "sess-1",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"response": "You reached billing."}


def test_chat_returns_default_reply_when_no_keyword_matches() -> None:
    response = client.post(
        "/chat",
        json={
            "message": "Hello there.",
            "history": [],
            "session_id": "sess-2",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"response": "I am a test bot. How can I help?"}


def test_chat_keyword_match_is_case_insensitive() -> None:
    response = client.post("/chat", json={"message": "BILLING question here."})

    assert response.status_code == 200
    assert response.json() == {"response": "You reached billing."}


def test_chat_history_field_is_optional() -> None:
    response = client.post("/chat", json={"message": "Hello."})

    assert response.status_code == 200
    assert "response" in response.json()


def test_chat_rejects_malformed_body() -> None:
    response = client.post("/chat", content=b"not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 422
