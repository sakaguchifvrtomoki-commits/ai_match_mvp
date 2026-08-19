import datetime
import io
import json
import os
from pathlib import Path
from typing import Any

import google.auth as google_auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from api.storage.base import (
    Conflict,
    InvalidData,
    NotFound,
    SessionData,
    Storage,
    StorageConfigurationError,
    Unavailable,
)


FOLDER_MIME = "application/vnd.google-apps.folder"
JSON_MIME = "application/json"
MARKDOWN_MIME = "text/markdown"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveStorage(Storage):
    """Google Drive storage with no Streamlit or request-local state dependencies."""

    def __init__(self, service: Any, root_folder_id: str):
        if service is None or not root_folder_id:
            raise Unavailable("Google Drive service and root folder are required")
        self.service = service
        self.root_folder_id = root_folder_id
        self._folder_cache: dict[tuple[str, str], str] = {}

    @classmethod
    def from_env(cls) -> "GoogleDriveStorage":
        root = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "").strip()
        if not root:
            raise Unavailable("GOOGLE_DRIVE_ROOT_FOLDER_ID is not configured")

        return cls(cls.build_service_from_env(), root)

    @classmethod
    def build_service_from_env(cls):
        """Build a Drive client without requiring a storage root folder."""

        auth_mode = os.getenv("GOOGLE_DRIVE_AUTH_MODE", "auto").strip().lower()
        if auth_mode not in {"auto", "user_oauth", "service_account", "adc"}:
            raise StorageConfigurationError(
                f"Unknown GOOGLE_DRIVE_AUTH_MODE: {auth_mode}"
            )

        try:
            raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
            if auth_mode == "user_oauth":
                credentials = cls._load_user_oauth_credentials()
            elif auth_mode == "service_account":
                if not raw:
                    raise Unavailable("GOOGLE_SERVICE_ACCOUNT_JSON is not configured")
                info = json.loads(raw)
                credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            elif auth_mode == "adc":
                credentials, _ = google_auth.default(scopes=SCOPES)
            elif raw:
                info = json.loads(raw)
                credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            else:
                credentials, _ = google_auth.default(scopes=SCOPES)
            return build("drive", "v3", credentials=credentials, cache_discovery=False)
        except (StorageConfigurationError, Unavailable):
            raise
        except Exception as exc:
            raise Unavailable("Google Drive authentication failed") from exc

    @classmethod
    def _load_user_oauth_credentials(cls) -> Credentials:
        raw = os.getenv("GOOGLE_OAUTH_CREDENTIALS_JSON", "").strip()
        if raw:
            try:
                info = json.loads(raw)
            except (TypeError, ValueError) as exc:
                raise Unavailable("Google OAuth token JSON is invalid") from exc
        else:
            token_path = Path(os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "token.json"))
            try:
                info = json.loads(token_path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise Unavailable(
                    f"Google OAuth token file was not found: {token_path}"
                ) from exc
            except (OSError, UnicodeError, ValueError) as exc:
                raise Unavailable("Google OAuth token file could not be read") from exc

        if not isinstance(info, dict):
            raise Unavailable("Google OAuth token JSON is invalid")
        try:
            credentials = Credentials.from_authorized_user_info(info, scopes=SCOPES)
        except Exception as exc:
            raise Unavailable("Google OAuth token JSON is invalid") from exc

        if not credentials.valid:
            if not credentials.refresh_token:
                raise Unavailable("Google OAuth refresh token is not available")
            try:
                credentials.refresh(Request())
            except Exception as exc:
                raise Unavailable("Google OAuth token refresh failed") from exc
            if not credentials.valid:
                raise Unavailable("Google OAuth token remains invalid after refresh")
        return credentials

    def _execute(self, request):
        try:
            return request.execute()
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status in (409, 412):
                raise Conflict("Google Drive revision conflict") from exc
            raise Unavailable("Google Drive API is unavailable") from exc

    def _list(self, *, parent: str, properties: dict[str, str], mime_type: str | None = None) -> list[dict]:
        clauses = [f"'{_escape(parent)}' in parents", "trashed = false"]
        if mime_type:
            clauses.append(f"mimeType = '{_escape(mime_type)}'")
        clauses.extend(f"appProperties has {{ key='{_escape(k)}' and value='{_escape(v)}' }}" for k, v in properties.items())
        result = self._execute(self.service.files().list(
            q=" and ".join(clauses), spaces="drive", fields="files(id,name,mimeType,appProperties,version)",
            pageSize=10, supportsAllDrives=True, includeItemsFromAllDrives=True,
        ))
        return result.get("files", [])

    def _find_one(self, *, parent: str, properties: dict[str, str], mime_type: str | None = None) -> dict | None:
        files = self._list(parent=parent, properties=properties, mime_type=mime_type)
        if len(files) > 1:
            raise Conflict("multiple Google Drive objects match the same identity")
        return files[0] if files else None

    def _folder(self, name: str, parent: str, properties: dict[str, str]) -> str:
        key = (parent, json.dumps(properties, sort_keys=True))
        if key in self._folder_cache:
            return self._folder_cache[key]
        found = self._find_one(parent=parent, properties=properties, mime_type=FOLDER_MIME)
        if found:
            folder_id = found["id"]
        else:
            folder_id = self._execute(self.service.files().create(
                body={"name": name, "parents": [parent], "mimeType": FOLDER_MIME, "appProperties": properties},
                fields="id", supportsAllDrives=True,
            ))["id"]
        self._folder_cache[key] = folder_id
        return folder_id

    def _path(self, parts: list[tuple[str, dict[str, str]]]) -> str:
        parent = self.root_folder_id
        for name, props in parts:
            parent = self._folder(name, parent, props)
        return parent

    def _download(self, file_id: str) -> bytes:
        data = self._execute(self.service.files().get_media(fileId=file_id, supportsAllDrives=True))
        if not isinstance(data, (bytes, bytearray)):
            raise InvalidData("Google Drive file content is invalid")
        return bytes(data)

    @staticmethod
    def _json_bytes(value: Any, label: str) -> bytes:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise InvalidData(f"{label} is not JSON serializable") from exc

    def _put(self, *, parent: str, name: str, data: bytes, mime_type: str,
             properties: dict[str, str], existing: dict | None = None) -> dict:
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)
        body = {"name": name, "appProperties": properties}
        if existing:
            return self._execute(self.service.files().update(
                fileId=existing["id"], body=body, media_body=media, fields="id,version", supportsAllDrives=True,
            ))
        body["parents"] = [parent]
        return self._execute(self.service.files().create(
            body=body, media_body=media, fields="id,version", supportsAllDrives=True,
        ))

    def _profile_parent(self) -> str:
        profiles = self._path([("profiles", {"data_type": "profiles_folder"})])
        return self._folder("current", profiles, {"data_type": "current_profiles_folder"})

    def load_profile(self, user_id: str) -> dict:
        parent = self._profile_parent()
        found = self._find_one(parent=parent, properties={"data_type": "current_profile", "user_id": user_id})
        if not found:
            raise NotFound(f"profile not found: {user_id}")
        try:
            value = json.loads(self._download(found["id"]).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidData("profile JSON is invalid") from exc
        if not isinstance(value, dict) or value.get("user_id") != user_id:
            raise InvalidData("profile identity is invalid")
        return value

    def save_profile(self, user_id: str, profile: dict) -> None:
        if profile.get("user_id") != user_id:
            raise InvalidData("profile user_id mismatch")
        data = self._json_bytes(profile, "profile")
        parent = self._profile_parent(); props = {"data_type": "current_profile", "user_id": user_id}
        self._put(parent=parent, name=f"{user_id}.json", data=data, mime_type=JSON_MIME,
                  properties=props, existing=self._find_one(parent=parent, properties=props))

    def save_profile_history(self, user_id, session_id, profile, stage):
        profiles = self._path([("profiles", {"data_type": "profiles_folder"})])
        history = self._folder("history", profiles, {"data_type": "profile_history_folder"})
        user_folder = self._folder(user_id, history, {"data_type": "profile_history_user_folder", "user_id": user_id})
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{user_id}_{stamp}_{session_id}{'_before' if stage == 'before' else ''}.json"
        props = {"data_type": "profile_history", "user_id": user_id, "session_id": session_id, "stage": stage}
        self._put(parent=user_folder, name=name, data=self._json_bytes(profile, "profile history"),
                  mime_type=JSON_MIME, properties=props)

    def backup_profile_before_migration(self, user_id):
        current = self._profile_parent(); props = {"data_type": "current_profile", "user_id": user_id}
        found = self._find_one(parent=current, properties=props)
        if not found: raise NotFound(f"profile not found: {user_id}")
        profiles = self._path([("profiles", {"data_type": "profiles_folder"})])
        backups = self._folder("migration_backups", profiles, {"data_type": "migration_backups_folder"})
        user_folder = self._folder(user_id, backups, {"data_type": "migration_backup_user_folder", "user_id": user_id})
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._put(parent=user_folder, name=f"{user_id}.{stamp}.pre_migration.bak", data=self._download(found["id"]),
                  mime_type=JSON_MIME, properties={"data_type": "migration_backup", "user_id": user_id, "source_file_id": found["id"]})

    def _sessions_parent(self) -> str:
        return self._path([("sessions", {"data_type": "sessions_folder"})])

    def _session_folder(self, session_id: str, create: bool) -> str:
        parent = self._sessions_parent(); props = {"data_type": "session_folder", "session_id": session_id}
        found = self._find_one(parent=parent, properties=props, mime_type=FOLDER_MIME)
        if found: return found["id"]
        if not create: raise NotFound(f"session not found: {session_id}")
        return self._folder(session_id, parent, props)

    def create_session(self, session_id, metadata, markdown):
        parent = self._sessions_parent(); props = {"data_type": "session_folder", "session_id": session_id}
        if self._find_one(parent=parent, properties=props, mime_type=FOLDER_MIME):
            raise Conflict(f"session already exists: {session_id}")
        folder = self._session_folder(session_id, True); clean = dict(metadata); clean.pop("started_at_compact", None); clean.pop("log_path", None)
        self._put(parent=folder, name="session.md", data=markdown.encode(), mime_type=MARKDOWN_MIME,
                  properties={"data_type": "session_markdown", "session_id": session_id})
        self._put(parent=folder, name="metadata.json", data=self._json_bytes(clean, "session metadata"), mime_type=JSON_MIME,
                  properties={"data_type": "session_metadata", "session_id": session_id})

    def load_session(self, session_id):
        folder = self._session_folder(session_id, False)
        md = self._find_one(parent=folder, properties={"data_type": "session_markdown", "session_id": session_id})
        meta = self._find_one(parent=folder, properties={"data_type": "session_metadata", "session_id": session_id})
        if not md or not meta: raise NotFound(f"session files not found: {session_id}")
        try: metadata = json.loads(self._download(meta["id"]).decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise InvalidData("session metadata JSON is invalid") from exc
        if not isinstance(metadata, dict) or metadata.get("session_id") != session_id:
            raise InvalidData("session metadata identity is invalid")
        try:
            markdown = self._download(md["id"]).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidData("session markdown is not UTF-8") from exc
        return SessionData(metadata, markdown)

    def update_session(self, session_id, metadata, markdown):
        folder = self._session_folder(session_id, False)
        md_props = {"data_type": "session_markdown", "session_id": session_id}
        meta_props = {"data_type": "session_metadata", "session_id": session_id}
        md = self._find_one(parent=folder, properties=md_props); meta = self._find_one(parent=folder, properties=meta_props)
        if not md or not meta: raise NotFound(f"session files not found: {session_id}")
        existing = self.load_session(session_id).metadata; existing.update(metadata); existing.pop("log_path", None)
        self._put(parent=folder, name="session.md", data=markdown.encode(), mime_type=MARKDOWN_MIME, properties=md_props, existing=md)
        self._put(parent=folder, name="metadata.json", data=self._json_bytes(existing, "session metadata"), mime_type=JSON_MIME, properties=meta_props, existing=meta)
