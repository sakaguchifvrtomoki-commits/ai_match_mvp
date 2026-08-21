from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.storage.base import NotFound, SessionData, StorageConfigurationError, Unavailable
from scripts import test_fastapi_google_drive_live as live_script


class FakeDriveStorage:
    def __init__(self):
        self.profiles = {}
        self.sessions = {}
        self.history = []

    def load_profile(self, user_id):
        if user_id not in self.profiles:
            raise NotFound(user_id)
        return deepcopy(self.profiles[user_id])

    def save_profile(self, user_id, profile):
        self.profiles[user_id] = deepcopy(profile)

    def save_profile_history(self, user_id, session_id, profile, stage):
        self.history.append((user_id, session_id, deepcopy(profile), stage))

    def backup_profile_before_migration(self, user_id):
        if user_id not in self.profiles:
            raise NotFound(user_id)

    def create_session(self, session_id, metadata, markdown):
        clean = deepcopy(metadata)
        clean.pop("started_at_compact", None)
        clean.pop("log_path", None)
        self.sessions[session_id] = SessionData(clean, markdown)

    def load_session(self, session_id):
        if session_id not in self.sessions:
            raise NotFound(session_id)
        value = self.sessions[session_id]
        return SessionData(deepcopy(value.metadata), value.markdown)

    def update_session(self, session_id, metadata, markdown):
        current = self.load_session(session_id)
        merged = deepcopy(current.metadata)
        merged.update(metadata)
        self.sessions[session_id] = SessionData(merged, markdown)


def test_live_integration_calls_all_endpoints_with_stubbed_ai(monkeypatch):
    storage = FakeDriveStorage()
    monkeypatch.setenv("FAIRIES_STORAGE_BACKEND", "google_drive")
    monkeypatch.setattr(
        live_script.GoogleDriveStorage,
        "from_env",
        classmethod(lambda cls: storage),
    )
    output = []

    with TestClient(app) as client:
        result = live_script.run_live_integration_test(
            client, storage, output=output.append
        )

    assert result.user_id.startswith("__fairies_api_drive_live_test_")
    assert result.user_id.endswith("__")
    assert result.session_id in storage.sessions
    assert storage.sessions[result.session_id].metadata["session_status"] == "completed"
    assert storage.sessions[result.session_id].metadata["end_reason"] == "user_clicked_finish"
    assert storage.profiles[result.user_id]["values"] == [
        "live integration test value"
    ]
    assert [item[3] for item in storage.history] == ["before", "after"]
    assert output[-3] == "FastAPI + Google Drive live integration test succeeded."


def test_chat_phase_does_not_save_an_empty_profile(monkeypatch):
    class FailOnProfileSave(FakeDriveStorage):
        def save_profile(self, user_id, profile):
            raise Unavailable("profile save reached later during match")

    storage = FailOnProfileSave()
    monkeypatch.setenv("FAIRIES_STORAGE_BACKEND", "google_drive")
    monkeypatch.setattr(
        live_script.GoogleDriveStorage,
        "from_env",
        classmethod(lambda cls: storage),
    )
    output = []

    with TestClient(app) as client:
        with pytest.raises(live_script.LiveApiTestFailure) as error:
            live_script.run_live_integration_test(
                client, storage, output=output.append
            )

    assert "[OK] POST /chat" in output
    assert error.value.stage == "POST /match"
    assert storage.profiles == {}


@pytest.mark.parametrize(
    ("backend", "auth_mode", "root_id", "expected"),
    [
        ("local", "user_oauth", "root", "FAIRIES_STORAGE_BACKEND"),
        ("google_drive", "adc", "root", "GOOGLE_DRIVE_AUTH_MODE"),
        ("google_drive", "user_oauth", "", "GOOGLE_DRIVE_ROOT_FOLDER_ID"),
    ],
)
def test_live_integration_requires_explicit_drive_environment(
    monkeypatch, backend, auth_mode, root_id, expected
):
    monkeypatch.setenv("FAIRIES_STORAGE_BACKEND", backend)
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", auth_mode)
    monkeypatch.setenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", root_id)
    monkeypatch.setattr(
        live_script.GoogleDriveStorage,
        "from_env",
        classmethod(lambda cls: pytest.fail("must not connect")),
    )

    with pytest.raises(StorageConfigurationError, match=expected):
        live_script._storage_from_env()
