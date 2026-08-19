from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import chat_service, match_service
from api.main import app
from api.storage.base import NotFound, SessionData, Storage, Unavailable
from api.storage.google_drive import GoogleDriveStorage


client = TestClient(app)
SESSION_ID = "session_20260819_120000_abcdef"
MESSAGES = [{"role": "assistant", "content": "こんにちは"},
            {"role": "user", "content": "本が好き"}, {"role": "user", "content": "信頼が大事"},
            {"role": "user", "content": "穏やかな人が好き"}]


class FakeDriveStorage(Storage):
    def __init__(self):
        self.profiles = {}; self.sessions = {}; self.calls = []; self.profile_error = None
    def load_profile(self, user_id):
        self.calls.append(("load_profile", user_id))
        if self.profile_error: raise self.profile_error
        if user_id not in self.profiles: raise NotFound
        return deepcopy(self.profiles[user_id])
    def save_profile(self, user_id, profile): self.calls.append(("save_profile", user_id)); self.profiles[user_id] = deepcopy(profile)
    def save_profile_history(self, user_id, session_id, profile, stage): self.calls.append(("history", stage))
    def backup_profile_before_migration(self, user_id): self.calls.append(("backup", user_id))
    def create_session(self, session_id, metadata, markdown):
        self.calls.append(("create_session", session_id)); clean = dict(metadata); clean.pop("started_at_compact", None)
        self.sessions[session_id] = SessionData(clean, markdown)
    def load_session(self, session_id):
        self.calls.append(("load_session", session_id))
        if session_id not in self.sessions: raise NotFound
        return self.sessions[session_id]
    def update_session(self, session_id, metadata, markdown):
        self.calls.append(("update_session", metadata.get("session_status")))
        current = self.load_session(session_id); merged = dict(current.metadata); merged.update(metadata)
        self.sessions[session_id] = SessionData(merged, markdown)


@pytest.fixture
def drive_backend(monkeypatch):
    storage = FakeDriveStorage()
    monkeypatch.setenv("FAIRIES_STORAGE_BACKEND", "google_drive")
    monkeypatch.setattr(GoogleDriveStorage, "from_env", classmethod(lambda cls: storage))
    return storage


def ai_client(content):
    create = lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_sessions_uses_drive_storage_and_response_is_unchanged(monkeypatch, drive_backend):
    monkeypatch.setattr("api.session_service.streamlit_app.get_openai_client", lambda: None)
    response = client.post("/sessions", json={"user_id": None, "log_consent": True})
    assert response.status_code == 201 and response.json()["message"]["role"] == "assistant"
    assert any(call[0] == "create_session" for call in drive_backend.calls)


def test_chat_reads_drive_profile_and_uses_memory(monkeypatch, drive_backend):
    profile = chat_service.streamlit_app._empty_profile("user_test")
    profile["summary"]["recent"] = "読書が好き"
    drive_backend.profiles["user_test"] = profile; captured = {}
    fake = ai_client("いいですね")
    original = fake.chat.completions.create
    fake.chat.completions.create = lambda **kw: captured.update(kw) or original(**kw)
    monkeypatch.setattr(chat_service.streamlit_app, "get_openai_client", lambda: fake)
    response = client.post("/chat", json={"user_id": "user_test", "session_id": SESSION_ID, "messages": MESSAGES})
    assert response.status_code == 200
    assert "読書が好き" in captured["messages"][0]["content"]


def test_chat_not_found_creates_only_in_memory_empty_profile(monkeypatch, drive_backend):
    monkeypatch.setattr(chat_service.streamlit_app, "get_openai_client", lambda: ai_client("返答"))
    assert client.post("/chat", json={"user_id": "new_user", "session_id": SESSION_ID, "messages": MESSAGES}).status_code == 200
    assert "new_user" not in drive_backend.profiles
    assert not any(c[0] == "save_profile" for c in drive_backend.calls)


def test_chat_unavailable_is_not_treated_as_not_found_or_saved(monkeypatch, drive_backend):
    drive_backend.profile_error = Unavailable("drive down")
    monkeypatch.setattr(chat_service.streamlit_app, "get_openai_client", lambda: ai_client("返答"))
    assert client.post("/chat", json={"user_id": "user_test", "session_id": SESSION_ID, "messages": MESSAGES}).status_code == 200
    assert not any(c[0] == "save_profile" for c in drive_backend.calls)


def _install_match_pipeline(monkeypatch, drive_backend):
    analysis = {"personality": "穏やか", "values": "信頼", "hidden_needs": "安心", "communication_style": "丁寧", "ideal_partner_type": "誠実", "summary": "要約"}
    candidate = {"id": "c01", "name": "葵", "age": 29, "personality": "穏やか", "values": "信頼", "hobbies": "読書", "communication_style": "丁寧", "relationship_style": "じっくり", "description": "誠実"}
    match = {"matched_candidate": candidate, "match_score": 90, "match_label": "安心感重視タイプ", "match_reason": "理由", "possible_concern": "注意", "recommended_first_message": "挨拶"}
    monkeypatch.setattr(match_service, "analyze_user", lambda *a: analysis)
    monkeypatch.setattr(match_service.streamlit_app, "load_candidates", lambda: [candidate])
    monkeypatch.setattr(match_service, "generate_match", lambda *a: (match, [{"candidate": candidate, "similarity": .9}]))
    monkeypatch.setattr(match_service, "generate_after_match_support", lambda *a: None)
    monkeypatch.setattr(match_service.streamlit_app, "get_openai_client", lambda: ai_client("{}"))
    drive_backend.sessions[SESSION_ID] = SessionData({"session_id": SESSION_ID, "user_id": "user_test"}, "start")


def test_match_uses_drive_profile_history_save_and_session_update(monkeypatch, drive_backend):
    _install_match_pipeline(monkeypatch, drive_backend)
    drive_backend.profiles["user_test"] = match_service.streamlit_app._empty_profile("user_test")
    response = client.post("/match", json={"user_id": "user_test", "session_id": SESSION_ID, "messages": MESSAGES})
    assert response.status_code == 200 and response.json()["profile_updated"] is True
    names = [c[0] for c in drive_backend.calls]
    assert "load_profile" in names and names.count("history") == 2 and "save_profile" in names and "update_session" in names


def test_match_drive_unavailable_keeps_partial_success_without_overwrite(monkeypatch, drive_backend):
    _install_match_pipeline(monkeypatch, drive_backend); drive_backend.profile_error = Unavailable("down")
    response = client.post("/match", json={"user_id": "user_test", "session_id": SESSION_ID, "messages": MESSAGES})
    assert response.status_code == 200 and response.json()["profile_updated"] is False
    assert not any(c[0] in {"save_profile", "history"} for c in drive_backend.calls)


def test_end_loads_and_completes_drive_session(drive_backend):
    drive_backend.sessions[SESSION_ID] = SessionData({"session_id": SESSION_ID, "user_id": "user_test", "started_at": "x", "log_consent": True, "consented_at": "x"}, "start")
    response = client.post(f"/sessions/{SESSION_ID}/end", json={"user_id": "user_test", "messages": MESSAGES})
    assert response.status_code == 200 and response.json() == {"status": "completed"}
    assert drive_backend.sessions[SESSION_ID].metadata["session_status"] == "completed"


def test_end_drive_unavailable_returns_session_end_failed(drive_backend):
    drive_backend.profile_error = None
    def fail(session_id): raise Unavailable("down")
    drive_backend.load_session = fail
    response = client.post(f"/sessions/{SESSION_ID}/end", json={"user_id": "user_test", "messages": MESSAGES})
    assert response.status_code == 500 and response.json()["error"]["code"] == "SESSION_END_FAILED"
