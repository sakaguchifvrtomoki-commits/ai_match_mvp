import pytest

import api.storage as storage_module
from api.storage.base import StorageConfigurationError
from api.storage.google_drive import GoogleDriveStorage
from api.storage.local import LocalStorage


def test_unset_defaults_to_local(monkeypatch):
    monkeypatch.delenv("FAIRIES_STORAGE_BACKEND", raising=False)
    assert isinstance(storage_module.get_storage(), LocalStorage)


def test_explicit_local(monkeypatch):
    monkeypatch.setenv("FAIRIES_STORAGE_BACKEND", "local")
    assert isinstance(storage_module.get_storage(), LocalStorage)


def test_google_drive_uses_from_env_without_real_auth(monkeypatch):
    sentinel = object()
    monkeypatch.setenv("FAIRIES_STORAGE_BACKEND", "google_drive")
    monkeypatch.setattr(GoogleDriveStorage, "from_env", classmethod(lambda cls: sentinel))
    assert storage_module.get_storage() is sentinel


@pytest.mark.parametrize("value", ["unknown", "", "LOCAL_DISK"])
def test_unknown_backend_is_configuration_error(monkeypatch, value):
    monkeypatch.setenv("FAIRIES_STORAGE_BACKEND", value)
    with pytest.raises(StorageConfigurationError):
        storage_module.get_storage()
