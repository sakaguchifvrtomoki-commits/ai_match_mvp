import inspect
import json

import pytest

import api.storage.google_drive as drive_module
from api.storage.base import StorageConfigurationError, Unavailable
from api.storage.google_drive import GoogleDriveStorage


class FakeCredentials:
    def __init__(self, *, valid=True, refresh_token="refresh-token", refresh_error=None):
        self.valid = valid
        self.refresh_token = refresh_token
        self.refresh_error = refresh_error
        self.refresh_calls = 0

    def refresh(self, request):
        self.refresh_calls += 1
        if self.refresh_error:
            raise self.refresh_error
        self.valid = True


@pytest.fixture(autouse=True)
def auth_environment(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "root-folder")
    for name in (
        "GOOGLE_DRIVE_AUTH_MODE",
        "GOOGLE_OAUTH_CREDENTIALS_JSON",
        "GOOGLE_OAUTH_TOKEN_FILE",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
    ):
        monkeypatch.delenv(name, raising=False)


def configure_oauth_mocks(monkeypatch, credentials):
    captured = {}

    class CredentialsFactory:
        @staticmethod
        def from_authorized_user_info(info, scopes):
            captured["info"] = info
            captured["scopes"] = scopes
            return credentials

    service = object()
    monkeypatch.setattr(drive_module, "Credentials", CredentialsFactory)
    monkeypatch.setattr(drive_module, "Request", lambda: object())
    monkeypatch.setattr(
        drive_module,
        "build",
        lambda api, version, **kwargs: captured.update(kwargs) or service,
    )
    return captured, service


def write_token(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text(
        json.dumps(
            {
                "token": "access-token",
                "refresh_token": "refresh-token",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "client-id",
                "client_secret": "client-secret",
            }
        ),
        encoding="utf-8",
    )
    return token_path


def test_user_oauth_loads_credentials_from_token_file(monkeypatch, tmp_path):
    credentials = FakeCredentials()
    captured, service = configure_oauth_mocks(monkeypatch, credentials)
    token_path = write_token(tmp_path)
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "user_oauth")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(token_path))

    storage = GoogleDriveStorage.from_env()

    assert storage.service is service
    assert captured["info"]["refresh_token"] == "refresh-token"
    assert captured["credentials"] is credentials


def test_user_oauth_can_load_credentials_json_from_environment(monkeypatch):
    credentials = FakeCredentials()
    captured, _ = configure_oauth_mocks(monkeypatch, credentials)
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "user_oauth")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_CREDENTIALS_JSON",
        json.dumps({"refresh_token": "secret-manager-value"}),
    )

    GoogleDriveStorage.from_env()

    assert captured["info"]["refresh_token"] == "secret-manager-value"


def test_expired_user_oauth_token_is_refreshed(monkeypatch, tmp_path):
    credentials = FakeCredentials(valid=False)
    configure_oauth_mocks(monkeypatch, credentials)
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "user_oauth")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(write_token(tmp_path)))

    GoogleDriveStorage.from_env()

    assert credentials.refresh_calls == 1
    assert credentials.valid is True


def test_user_oauth_refresh_failure_is_unavailable(monkeypatch, tmp_path):
    credentials = FakeCredentials(valid=False, refresh_error=RuntimeError("refresh failed"))
    configure_oauth_mocks(monkeypatch, credentials)
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "user_oauth")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(write_token(tmp_path)))

    with pytest.raises(Unavailable, match="refresh"):
        GoogleDriveStorage.from_env()


def test_missing_user_oauth_token_file_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "user_oauth")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(tmp_path / "missing.json"))

    with pytest.raises(Unavailable, match="not found"):
        GoogleDriveStorage.from_env()


def test_invalid_user_oauth_token_is_unavailable(monkeypatch, tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("not-json", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "user_oauth")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(token_path))

    with pytest.raises(Unavailable, match="could not be read"):
        GoogleDriveStorage.from_env()


def test_service_account_mode_is_preserved(monkeypatch):
    credentials = object()
    service = object()
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "service_account")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps({"type": "service_account"}))
    monkeypatch.setattr(
        drive_module.service_account.Credentials,
        "from_service_account_info",
        lambda info, scopes: credentials,
    )
    monkeypatch.setattr(drive_module, "build", lambda *args, **kwargs: service)

    assert GoogleDriveStorage.from_env().service is service


def test_adc_mode_is_preserved(monkeypatch):
    credentials = object()
    service = object()
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "adc")
    monkeypatch.setattr(drive_module.google_auth, "default", lambda scopes: (credentials, "project"))
    monkeypatch.setattr(drive_module, "build", lambda *args, **kwargs: service)

    assert GoogleDriveStorage.from_env().service is service


def test_unknown_auth_mode_is_configuration_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "mystery")
    with pytest.raises(StorageConfigurationError):
        GoogleDriveStorage.from_env()


def test_google_drive_storage_has_no_streamlit_dependency():
    source = inspect.getsource(drive_module)
    assert "import streamlit" not in source
    assert "st.secrets" not in source
    assert "st.session_state" not in source
