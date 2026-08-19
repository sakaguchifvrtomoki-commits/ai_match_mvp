from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import chat_service
from api.main import app


client = TestClient(app)
VALID_REQUEST = {
    "user_id": "user_test",
    "session_id": "session_20260819_120000_abcdef",
    "messages": [
        {"role": "assistant", "content": "こんにちは。"},
        {"role": "user", "content": "今日は読書の話をしたいです。"},
    ],
}


def fake_openai_response(content="いいですね。どんな本を読んでいますか？", finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content),
            )
        ]
    )


def install_fake_client(monkeypatch, create):
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(chat_service.streamlit_app, "get_openai_client", lambda: fake_client)


def test_chat_returns_assistant_message_and_does_not_mutate_history(monkeypatch):
    request_body = deepcopy(VALID_REQUEST)
    original = deepcopy(request_body)
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return fake_openai_response()

    install_fake_client(monkeypatch, create)
    monkeypatch.setattr(chat_service, "load_user_profile", lambda user_id: {})

    response = client.post("/chat", json=request_body)

    assert response.status_code == 200
    assert response.json() == {
        "message": {
            "role": "assistant",
            "content": "いいですね。どんな本を読んでいますか？",
        }
    }
    assert request_body == original
    assert captured["messages"][1:] == original["messages"]


def test_chat_uses_profile_memory_and_prioritization_rules(monkeypatch):
    profile = {
        "summary": {"recent": "読書が好き", "stable": ""},
        "personality_traits": {},
        "values": [],
        "preferences": {},
        "matching_hypothesis": {},
    }
    captured = {}

    monkeypatch.setattr(
        chat_service, "load_user_profile", lambda user_id: profile
    )

    def create(**kwargs):
        captured.update(kwargs)
        return fake_openai_response()

    install_fake_client(monkeypatch, create)

    response = client.post("/chat", json=VALID_REQUEST)

    assert response.status_code == 200
    system_prompt = captured["messages"][0]["content"]
    assert "ユーザーの特徴: 読書が好き" in system_prompt
    assert "今回のユーザーの発言を最優先してください" in system_prompt


def test_profile_load_failure_continues_without_overwriting_profile(monkeypatch):
    def fail_load(user_id):
        raise RuntimeError("profile unavailable")

    monkeypatch.setattr(chat_service, "load_user_profile", fail_load)
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return fake_openai_response()

    install_fake_client(monkeypatch, create)

    response = client.post("/chat", json=VALID_REQUEST)

    assert response.status_code == 200
    assert "【背景情報】" not in captured["messages"][0]["content"]


@pytest.mark.parametrize(
    "body",
    [
        {"session_id": VALID_REQUEST["session_id"], "messages": VALID_REQUEST["messages"]},
        {"user_id": "user_test", "messages": VALID_REQUEST["messages"]},
        {**VALID_REQUEST, "messages": []},
        {**VALID_REQUEST, "messages": [{"role": "system", "content": "bad"}]},
        {**VALID_REQUEST, "messages": [{"role": "user", "content": "   "}]},
        {**VALID_REQUEST, "user_id": "invalid/user"},
        {**VALID_REQUEST, "session_id": "invalid"},
    ],
)
def test_invalid_chat_request_uses_common_error_format(body):
    response = client.post("/chat", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_missing_openai_client_returns_ai_response_failed(monkeypatch):
    monkeypatch.setattr(chat_service.streamlit_app, "get_openai_client", lambda: None)

    response = client.post("/chat", json=VALID_REQUEST)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_FAILED"
    assert "message" not in response.json()


def test_ai_exception_returns_ai_response_failed(monkeypatch):
    def create(**kwargs):
        raise RuntimeError("network error")

    install_fake_client(monkeypatch, create)
    monkeypatch.setattr(chat_service, "load_user_profile", lambda user_id: {})

    response = client.post("/chat", json=VALID_REQUEST)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_FAILED"


def test_finish_reason_length_returns_truncated_error(monkeypatch):
    install_fake_client(
        monkeypatch, lambda **kwargs: fake_openai_response("途中の応答", "length")
    )
    monkeypatch.setattr(chat_service, "load_user_profile", lambda user_id: {})

    response = client.post("/chat", json=VALID_REQUEST)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_TRUNCATED"
    assert "message" not in response.json()


def test_context_length_error_is_distinguished(monkeypatch):
    def create(**kwargs):
        raise RuntimeError("This model's maximum context length was exceeded")

    install_fake_client(monkeypatch, create)
    monkeypatch.setattr(chat_service, "load_user_profile", lambda user_id: {})

    response = client.post("/chat", json=VALID_REQUEST)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "AI_CONTEXT_TOO_LONG"


@pytest.mark.parametrize("content", ["", "   ", None])
def test_empty_ai_response_returns_ai_response_failed(monkeypatch, content):
    install_fake_client(monkeypatch, lambda **kwargs: fake_openai_response(content))
    monkeypatch.setattr(chat_service, "load_user_profile", lambda user_id: {})

    response = client.post("/chat", json=VALID_REQUEST)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_FAILED"


def test_only_chat_endpoint_is_added_for_this_step():
    paths = {route.path for route in app.routes}

    assert "/chat" in paths
    assert "/match" not in paths
    assert "/sessions/{session_id}/end" not in paths
