from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import session_service
from api.main import app


client = TestClient(app)


@pytest.fixture
def session_log_dir(monkeypatch, tmp_path):
    fake_app_file = tmp_path / "app.py"
    monkeypatch.setattr(session_service.streamlit_app, "__file__", str(fake_app_file))
    return tmp_path / "logs" / "0.2.2" / "sessions"


def test_create_session_for_new_user_uses_fallback_and_writes_log(
    monkeypatch, session_log_dir
):
    monkeypatch.setattr(session_service.streamlit_app, "get_openai_client", lambda: None)

    response = client.post("/sessions", json={"user_id": None, "log_consent": True})

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"].startswith("user_")
    assert body["session_id"].startswith("session_")
    assert body["message"] == {
        "role": "assistant",
        "content": session_service.INITIAL_GREETING_FALLBACK,
    }
    markdown_logs = list(session_log_dir.glob("*.md"))
    metadata_logs = list(session_log_dir.glob("*.json"))
    assert len(markdown_logs) == 1
    assert len(metadata_logs) == 1
    log_text = markdown_logs[0].read_text(encoding="utf-8")
    assert f"- user_id: {body['user_id']}" in log_text
    assert f"- session_id: {body['session_id']}" in log_text
    assert "- log_consent: true" in log_text
    assert "- session_status: started" in log_text


def test_create_session_preserves_valid_existing_user_id(monkeypatch, session_log_dir):
    monkeypatch.setattr(session_service.streamlit_app, "get_openai_client", lambda: None)

    response = client.post(
        "/sessions", json={"user_id": "existing_user-01", "log_consent": True}
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == "existing_user-01"


def test_each_request_creates_a_new_session_id(monkeypatch, session_log_dir):
    monkeypatch.setattr(session_service.streamlit_app, "get_openai_client", lambda: None)

    first = client.post("/sessions", json={"user_id": "user_1", "log_consent": True})
    second = client.post("/sessions", json={"user_id": "user_1", "log_consent": True})

    assert first.status_code == second.status_code == 201
    assert first.json()["session_id"] != second.json()["session_id"]


def test_log_consent_false_does_not_start_session(monkeypatch, session_log_dir):
    called = False

    def fail_if_called():
        nonlocal called
        called = True

    monkeypatch.setattr(session_service.streamlit_app, "generate_session_id", fail_if_called)

    response = client.post("/sessions", json={"user_id": None, "log_consent": False})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert not called
    assert not session_log_dir.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": None},
        {"user_id": None, "log_consent": "true"},
        {"user_id": "", "log_consent": True},
        {"user_id": "invalid/user", "log_consent": True},
    ],
)
def test_invalid_request_uses_common_error_format(payload, session_log_dir):
    response = client.post("/sessions", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_ai_greeting_is_returned_without_profile_or_streamlit_state(
    monkeypatch, session_log_dir
):
    create = lambda **kwargs: SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="今日は何について話してみたいですか？"),
            )
        ]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(
        session_service.streamlit_app, "get_openai_client", lambda: fake_client
    )

    response = client.post("/sessions", json={"user_id": None, "log_consent": True})

    assert response.status_code == 201
    assert response.json()["message"]["content"] == "今日は何について話してみたいですか？"


def test_ai_failure_uses_fallback_but_session_still_succeeds(
    monkeypatch, session_log_dir
):
    def raise_api_error(**kwargs):
        raise RuntimeError("API failed")

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=raise_api_error))
    )
    monkeypatch.setattr(
        session_service.streamlit_app, "get_openai_client", lambda: fake_client
    )

    response = client.post("/sessions", json={"user_id": None, "log_consent": True})

    assert response.status_code == 201
    assert response.json()["message"]["content"] == session_service.INITIAL_GREETING_FALLBACK


def test_log_write_failure_returns_error_and_does_not_call_ai(monkeypatch):
    monkeypatch.setattr(
        session_service,
        "create_initial_session_log",
        lambda **kwargs: (_ for _ in ()).throw(
            session_service.SessionStartError("初期セッションログを作成できませんでした。")
        ),
    )
    ai_called = False

    def get_client():
        nonlocal ai_called
        ai_called = True

    monkeypatch.setattr(session_service.streamlit_app, "get_openai_client", get_client)

    response = client.post("/sessions", json={"user_id": None, "log_consent": True})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "SESSION_START_FAILED"
    assert not ai_called


def test_endpoints_after_sessions_step_are_not_added():
    paths = {route.path for route in app.routes}

    assert "/chat" in paths
    assert "/match" in paths
    assert "/sessions/{session_id}/end" in paths
