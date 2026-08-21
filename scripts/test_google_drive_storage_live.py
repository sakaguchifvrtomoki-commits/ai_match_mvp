"""Explicit, developer-run live test for GoogleDriveStorage.

This file is intentionally not a pytest test. It connects to Google Drive only
when executed directly by a developer.
"""

import datetime
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.storage.base import NotFound, StorageConfigurationError, StorageError
from api.storage.google_drive import GoogleDriveStorage


@dataclass(frozen=True)
class LiveTestResult:
    user_id: str
    session_id: str


class LiveTestFailure(RuntimeError):
    def __init__(self, stage: str, cause: Exception):
        super().__init__(f"{stage}: {type(cause).__name__}: {cause}")
        self.stage = stage
        self.cause = cause


def _test_ids() -> tuple[str, str]:
    suffix = uuid.uuid4().hex
    return (
        f"__fairies_drive_live_test_{suffix}__",
        f"__fairies_drive_live_session_{suffix}__",
    )


def run_live_test(
    storage,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    output: Callable[[str], None] = print,
) -> LiveTestResult:
    generated_user_id, generated_session_id = _test_ids()
    user_id = user_id or generated_user_id
    session_id = session_id or generated_session_id
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    stage = "profile NotFound"

    try:
        try:
            storage.load_profile(user_id)
        except NotFound:
            output("[OK] profile NotFound")
        else:
            raise RuntimeError("test profile unexpectedly already exists")

        profile = {
            "user_id": user_id,
            "profile_version": "0.2.1",
            "summary": "Google Drive live storage test profile",
            "update_count": 0,
            "last_session_id": session_id,
            "last_updated": now,
        }
        stage = "profile saved"
        storage.save_profile(user_id, profile)
        output("[OK] profile saved")

        stage = "profile loaded"
        if storage.load_profile(user_id) != profile:
            raise RuntimeError("loaded profile does not match saved profile")
        output("[OK] profile loaded")

        updated_profile = dict(profile)
        updated_profile["summary"] = "Google Drive live storage test profile updated"
        updated_profile["update_count"] = 1
        stage = "profile updated"
        storage.save_profile(user_id, updated_profile)
        if storage.load_profile(user_id) != updated_profile:
            raise RuntimeError("profile update was not persisted")
        output("[OK] profile updated")

        stage = "profile history saved"
        storage.save_profile_history(
            user_id, session_id, updated_profile, "after"
        )
        output("[OK] profile history saved")

        stage = "migration backup saved"
        storage.backup_profile_before_migration(user_id)
        output("[OK] migration backup saved")

        metadata = {
            "session_id": session_id,
            "user_id": user_id,
            "session_status": "started",
            "started_at": now,
            "log_consent": True,
        }
        initial_markdown = "# Google Drive live storage test\n\nstatus: started\n"
        stage = "session created"
        storage.create_session(session_id, metadata, initial_markdown)
        output("[OK] session created")

        stage = "session loaded"
        loaded_session = storage.load_session(session_id)
        if loaded_session.metadata != metadata:
            raise RuntimeError("loaded session metadata does not match")
        if loaded_session.markdown != initial_markdown:
            raise RuntimeError("loaded session markdown does not match")
        output("[OK] session loaded")

        completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        completed_markdown = (
            "# Google Drive live storage test\n\nstatus: completed\n"
        )
        stage = "session updated"
        storage.update_session(
            session_id,
            {
                "session_status": "completed",
                "end_reason": "live_storage_test",
                "ended_at": completed_at,
            },
            completed_markdown,
        )
        loaded_session = storage.load_session(session_id)
        if loaded_session.metadata.get("session_status") != "completed":
            raise RuntimeError("session status was not updated")
        if loaded_session.metadata.get("end_reason") != "live_storage_test":
            raise RuntimeError("session end_reason was not updated")
        if loaded_session.markdown != completed_markdown:
            raise RuntimeError("session markdown was not updated")
        output("[OK] session updated")
    except LiveTestFailure:
        raise
    except Exception as exc:
        raise LiveTestFailure(stage, exc) from exc

    output("Google Drive live storage test succeeded.")
    output(f"Test user ID: {user_id}")
    output(f"Test session ID: {session_id}")
    return LiveTestResult(user_id=user_id, session_id=session_id)


def _storage_from_env() -> GoogleDriveStorage:
    backend = os.getenv("FAIRIES_STORAGE_BACKEND", "").strip().lower()
    if backend != "google_drive":
        raise StorageConfigurationError(
            "FAIRIES_STORAGE_BACKEND must be google_drive for the live test"
        )
    auth_mode = os.getenv("GOOGLE_DRIVE_AUTH_MODE", "").strip().lower()
    if auth_mode != "user_oauth":
        raise StorageConfigurationError(
            "GOOGLE_DRIVE_AUTH_MODE must be user_oauth for the live test"
        )
    if not os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "").strip():
        raise StorageConfigurationError(
            "GOOGLE_DRIVE_ROOT_FOLDER_ID is not configured"
        )
    return GoogleDriveStorage.from_env()


def main() -> int:
    storage = _storage_from_env()
    run_live_test(storage)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LiveTestFailure, StorageError) as exc:
        print(f"[FAILED] {exc}", file=sys.stderr)
        raise SystemExit(1)
