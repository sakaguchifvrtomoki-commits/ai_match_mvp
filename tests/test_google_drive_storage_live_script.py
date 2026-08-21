from copy import deepcopy

import pytest

from api.storage.base import NotFound, SessionData, StorageConfigurationError, Unavailable
from scripts import test_google_drive_storage_live as live_script


class FakeStorage:
    def __init__(self):
        self.profiles = {}
        self.sessions = {}
        self.history = []
        self.backups = []

    def load_profile(self, user_id):
        if user_id not in self.profiles:
            raise NotFound(f"profile not found: {user_id}")
        return deepcopy(self.profiles[user_id])

    def save_profile(self, user_id, profile):
        self.profiles[user_id] = deepcopy(profile)

    def save_profile_history(self, user_id, session_id, profile, stage):
        self.history.append((user_id, session_id, deepcopy(profile), stage))

    def backup_profile_before_migration(self, user_id):
        if user_id not in self.profiles:
            raise NotFound(user_id)
        self.backups.append((user_id, deepcopy(self.profiles[user_id])))

    def create_session(self, session_id, metadata, markdown):
        self.sessions[session_id] = SessionData(deepcopy(metadata), markdown)

    def load_session(self, session_id):
        if session_id not in self.sessions:
            raise NotFound(session_id)
        value = self.sessions[session_id]
        return SessionData(deepcopy(value.metadata), value.markdown)

    def update_session(self, session_id, metadata, markdown):
        existing = self.sessions[session_id]
        merged = deepcopy(existing.metadata)
        merged.update(metadata)
        self.sessions[session_id] = SessionData(merged, markdown)


def test_live_test_exercises_storage_with_unique_test_only_ids():
    storage = FakeStorage()
    output = []

    result = live_script.run_live_test(storage, output=output.append)

    assert result.user_id.startswith("__fairies_drive_live_test_")
    assert result.user_id.endswith("__")
    assert result.session_id.startswith("__fairies_drive_live_session_")
    assert result.session_id.endswith("__")
    assert storage.profiles[result.user_id]["update_count"] == 1
    assert storage.history[0][0:2] == (result.user_id, result.session_id)
    assert storage.history[0][3] == "after"
    assert storage.backups[0][0] == result.user_id
    assert storage.sessions[result.session_id].metadata["session_status"] == "completed"
    assert output[-3] == "Google Drive live storage test succeeded."


def test_existing_test_profile_stops_before_any_write():
    storage = FakeStorage()
    user_id = "__fairies_drive_live_test_fixed__"
    storage.profiles[user_id] = {"user_id": user_id}

    with pytest.raises(live_script.LiveTestFailure) as error:
        live_script.run_live_test(
            storage,
            user_id=user_id,
            session_id="__fairies_drive_live_session_fixed__",
            output=lambda message: None,
        )

    assert error.value.stage == "profile NotFound"
    assert storage.history == []
    assert storage.sessions == {}


def test_storage_exception_keeps_stage_and_exception_classification():
    class UnavailableStorage(FakeStorage):
        def save_profile(self, user_id, profile):
            raise Unavailable("Drive offline")

    with pytest.raises(live_script.LiveTestFailure) as error:
        live_script.run_live_test(
            UnavailableStorage(),
            user_id="__fairies_drive_live_test_fixed__",
            session_id="__fairies_drive_live_session_fixed__",
            output=lambda message: None,
        )

    assert error.value.stage == "profile saved"
    assert isinstance(error.value.cause, Unavailable)
    assert "Unavailable" in str(error.value)


@pytest.mark.parametrize(
    ("backend", "auth_mode", "root_id", "expected"),
    [
        ("local", "user_oauth", "root", "FAIRIES_STORAGE_BACKEND"),
        ("google_drive", "adc", "root", "GOOGLE_DRIVE_AUTH_MODE"),
        ("google_drive", "user_oauth", "", "GOOGLE_DRIVE_ROOT_FOLDER_ID"),
    ],
)
def test_live_storage_requires_explicit_safe_environment(
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
