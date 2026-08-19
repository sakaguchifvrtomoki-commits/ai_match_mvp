"""Create the app-owned Fairies_Test folder in the current user's My Drive."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.storage.base import Conflict, StorageConfigurationError, Unavailable
from api.storage.google_drive import FOLDER_MIME, GoogleDriveStorage


FOLDER_NAME = "Fairies_Test"
APP_PROPERTIES = {
    "data_type": "fairies_test_root",
    "app_id": "fairies_v0_2_2",
}


def _execute(request):
    try:
        return request.execute()
    except Exception as exc:
        raise Unavailable("Google Drive API is unavailable") from exc


def get_or_create_test_root(service) -> str:
    query = (
        "'root' in parents and trashed = false "
        f"and mimeType = '{FOLDER_MIME}' "
        "and appProperties has { key='data_type' and value='fairies_test_root' } "
        "and appProperties has { key='app_id' and value='fairies_v0_2_2' }"
    )
    result = _execute(
        service.files().list(
            q=query,
            spaces="drive",
            fields="files(id,name,appProperties)",
            pageSize=10,
        )
    )
    matches = result.get("files", [])
    if len(matches) > 1:
        raise Conflict("multiple Fairies test root folders were found")
    if matches:
        return matches[0]["id"]

    created = _execute(
        service.files().create(
            body={
                "name": FOLDER_NAME,
                "parents": ["root"],
                "mimeType": FOLDER_MIME,
                "appProperties": APP_PROPERTIES,
            },
            fields="id",
        )
    )
    folder_id = created.get("id")
    if not folder_id:
        raise Unavailable("Google Drive did not return the created folder ID")
    return folder_id


def main() -> int:
    auth_mode = os.getenv("GOOGLE_DRIVE_AUTH_MODE", "").strip().lower()
    if auth_mode != "user_oauth":
        raise StorageConfigurationError(
            "GOOGLE_DRIVE_AUTH_MODE must be user_oauth for this bootstrap script"
        )
    service = GoogleDriveStorage.build_service_from_env()
    folder_id = get_or_create_test_root(service)
    print(f"GOOGLE_DRIVE_ROOT_FOLDER_ID={folder_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
