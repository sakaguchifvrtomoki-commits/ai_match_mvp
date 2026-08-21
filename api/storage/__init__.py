import os
from pathlib import Path
import app as streamlit_app
from api.storage.base import Storage, StorageConfigurationError
from api.storage.google_drive import GoogleDriveStorage
from api.storage.local import LocalStorage


def get_storage() -> Storage:
    backend = os.getenv("FAIRIES_STORAGE_BACKEND", "local").strip().lower()
    if backend == "local":
        return LocalStorage(Path(streamlit_app.__file__).parent)
    if backend == "google_drive":
        return GoogleDriveStorage.from_env()
    raise StorageConfigurationError(
        f"Unsupported FAIRIES_STORAGE_BACKEND: {backend or '<empty>'}"
    )


__all__ = ["get_storage", "LocalStorage", "GoogleDriveStorage"]
