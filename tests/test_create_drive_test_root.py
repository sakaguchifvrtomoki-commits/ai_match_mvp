import pytest

from api.storage.base import Conflict, StorageConfigurationError, Unavailable
from scripts import create_drive_test_root as bootstrap


class Request:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class Files:
    def __init__(self, matches=None):
        self.matches = [] if matches is None else matches
        self.list_kwargs = None
        self.create_kwargs = None

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return Request({"files": self.matches})

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return Request({"id": "created-folder-id"})


class Service:
    def __init__(self, matches=None):
        self.api = Files(matches)

    def files(self):
        return self.api


PARENT_ID = "personal-ai-matching-folder-id"


def test_creates_fairies_test_under_configured_parent_with_app_properties():
    service = Service()

    folder_id = bootstrap.get_or_create_test_root(service, PARENT_ID)

    assert folder_id == "created-folder-id"
    body = service.api.create_kwargs["body"]
    assert body == {
        "name": "Fairies_Test",
        "parents": [PARENT_ID],
        "mimeType": "application/vnd.google-apps.folder",
        "appProperties": {
            "data_type": "fairies_test_root",
            "app_id": "fairies_v0_2_2",
        },
    }


def test_returns_existing_app_owned_test_root_without_creating():
    service = Service(
        [{"id": "existing-folder-id", "name": "Fairies_Test"}]
    )

    folder_id = bootstrap.get_or_create_test_root(service, PARENT_ID)

    assert folder_id == "existing-folder-id"
    assert service.api.create_kwargs is None
    query = service.api.list_kwargs["q"]
    assert f"'{PARENT_ID}' in parents" in query
    assert "'root' in parents" not in query
    assert "name = 'Fairies_Test'" in query
    assert "fairies_test_root" in query
    assert "fairies_v0_2_2" in query


def test_multiple_app_owned_roots_are_a_conflict():
    service = Service([{"id": "one"}, {"id": "two"}])
    with pytest.raises(Conflict):
        bootstrap.get_or_create_test_root(service, PARENT_ID)


def test_drive_failure_is_unavailable():
    class FailingFiles(Files):
        def list(self, **kwargs):
            return Request(error=RuntimeError("offline"))

    service = Service()
    service.api = FailingFiles()
    with pytest.raises(Unavailable):
        bootstrap.get_or_create_test_root(service, PARENT_ID)


def test_same_name_without_matching_app_properties_is_not_reused():
    service = Service(matches=[])

    folder_id = bootstrap.get_or_create_test_root(service, PARENT_ID)

    assert folder_id == "created-folder-id"
    query = service.api.list_kwargs["q"]
    assert "name = 'Fairies_Test'" in query
    assert "data_type' and value='fairies_test_root" in query
    assert "app_id' and value='fairies_v0_2_2" in query


def test_parent_folder_id_is_required_before_drive_access():
    service = Service()
    with pytest.raises(StorageConfigurationError):
        bootstrap.get_or_create_test_root(service, "")
    assert service.api.list_kwargs is None


def test_main_uses_oauth_service_and_prints_environment_setting(monkeypatch, capsys):
    service = Service([{"id": "existing-folder-id"}])
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "user_oauth")
    monkeypatch.setenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", PARENT_ID)
    monkeypatch.setattr(
        bootstrap.GoogleDriveStorage,
        "build_service_from_env",
        classmethod(lambda cls: service),
    )

    assert bootstrap.main() == 0
    assert capsys.readouterr().out.strip() == (
        "GOOGLE_DRIVE_ROOT_FOLDER_ID=existing-folder-id"
    )


def test_main_rejects_non_user_oauth_mode(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "adc")
    with pytest.raises(StorageConfigurationError):
        bootstrap.main()


def test_main_rejects_missing_parent_folder_id_before_auth(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "user_oauth")
    monkeypatch.delenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", raising=False)
    with pytest.raises(StorageConfigurationError, match="PARENT_FOLDER_ID"):
        bootstrap.main()
