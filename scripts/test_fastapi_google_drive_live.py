"""Developer-run live integration test for FastAPI and GoogleDriveStorage."""

import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from api.main import app
from api.storage.base import NotFound, StorageConfigurationError, StorageError
from api.storage.google_drive import GoogleDriveStorage


ANALYSIS = {
    "personality": "穏やか",
    "values": "信頼",
    "hidden_needs": "安心",
    "communication_style": "丁寧",
    "ideal_partner_type": "誠実な人",
    "summary": "固定stubによるlive integration test分析",
}
CANDIDATE = {
    "id": "live-test-candidate",
    "name": "テスト候補",
    "age": 30,
    "personality": "穏やか",
    "values": "信頼",
    "hobbies": "読書",
    "communication_style": "丁寧",
    "relationship_style": "じっくり",
    "description": "live integration test専用候補",
}
MATCH = {
    "matched_candidate": CANDIDATE,
    "match_score": 90,
    "match_label": "live testタイプ",
    "match_reason": "固定stubによるマッチ理由",
    "possible_concern": "固定stubによる注意点",
    "recommended_first_message": "こんにちは",
}
TOP_CANDIDATES = [{"candidate": CANDIDATE, "similarity": 0.9}]
AFTER_MATCH_SUPPORT = {
    "first_message_today": "こんにちは",
    "question_in_3days": "最近読んだ本はありますか？",
    "avoid_phrase": "固定stubの避ける表現",
    "slow_reply_action": "落ち着いて待つ",
}
PROFILE_DIFF = {
    "new_values": ["live integration test value"],
    "summary": {"new_tensions": []},
}


@dataclass(frozen=True)
class LiveApiTestResult:
    user_id: str
    session_id: str


class LiveApiTestFailure(RuntimeError):
    def __init__(self, stage: str, cause: Exception):
        super().__init__(f"{stage}: {type(cause).__name__}: {cause}")
        self.stage = stage
        self.cause = cause


def _ai_client(content: str):
    def create(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=content),
                )
            ]
        )

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def _expect_status(response, expected: int) -> dict:
    if response.status_code != expected:
        raise RuntimeError(
            f"expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    return response.json()


def run_live_integration_test(
    client: TestClient,
    verification_storage: GoogleDriveStorage,
    *,
    user_id: str | None = None,
    output=print,
) -> LiveApiTestResult:
    user_id = user_id or f"__fairies_api_drive_live_test_{uuid.uuid4().hex}__"
    stage = "test profile isolation"
    try:
        try:
            verification_storage.load_profile(user_id)
        except NotFound:
            pass
        else:
            raise RuntimeError("test profile unexpectedly already exists")

        stage = "POST /sessions"
        with patch(
            "api.session_service.generate_initial_greeting",
            return_value="固定stubの初回挨拶です。",
        ):
            response = client.post(
                "/sessions", json={"user_id": user_id, "log_consent": True}
            )
        session_result = _expect_status(response, 201)
        if session_result.get("user_id") != user_id:
            raise RuntimeError("POST /sessions returned a different user_id")
        session_id = session_result.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise RuntimeError("POST /sessions did not return a session_id")
        if not session_result.get("message", {}).get("content"):
            raise RuntimeError("POST /sessions did not return an assistant message")
        created_session = verification_storage.load_session(session_id)
        if created_session.metadata.get("user_id") != user_id:
            raise RuntimeError("Drive session metadata user_id does not match")
        output("[OK] POST /sessions")

        chat_messages = [
            session_result["message"],
            {"role": "user", "content": "これはlive integration testです。"},
        ]
        stage = "POST /chat"
        with patch(
            "api.chat_service.streamlit_app.get_openai_client",
            return_value=_ai_client("固定stubのチャット応答です。"),
        ):
            response = client.post(
                "/chat",
                json={
                    "user_id": user_id,
                    "session_id": session_id,
                    "messages": chat_messages,
                },
            )
        chat_result = _expect_status(response, 200)
        if not chat_result.get("message", {}).get("content"):
            raise RuntimeError("POST /chat did not return an assistant message")
        try:
            verification_storage.load_profile(user_id)
        except NotFound:
            pass
        else:
            raise RuntimeError("POST /chat unexpectedly persisted an empty profile")
        output("[OK] POST /chat")

        messages = [
            session_result["message"],
            {"role": "user", "content": "本を読むことが好きです。"},
            {"role": "assistant", "content": "どんな点が好きですか？"},
            {"role": "user", "content": "落ち着いて考えられるところです。"},
            {"role": "assistant", "content": "大切にしていることはありますか？"},
            {"role": "user", "content": "信頼を大切にしています。"},
        ]
        stage = "POST /match"
        with (
            patch("api.match_service.analyze_user", return_value=ANALYSIS),
            patch(
                "api.match_service.streamlit_app.load_candidates",
                return_value=[CANDIDATE],
            ),
            patch(
                "api.match_service.generate_match",
                return_value=(MATCH, TOP_CANDIDATES),
            ),
            patch(
                "api.match_service.generate_after_match_support",
                return_value=AFTER_MATCH_SUPPORT,
            ),
            patch(
                "api.match_service.streamlit_app.get_openai_client",
                return_value=_ai_client(json.dumps(PROFILE_DIFF)),
            ),
            patch(
                "api.match_service.streamlit_app.load_profile_extraction_prompt",
                return_value=(
                    "{{CONVERSATION}}\n{{EXISTING_PROFILE}}\n"
                    "{{USER_ID}}\n{{SESSION_ID}}"
                ),
            ),
        ):
            response = client.post(
                "/match",
                json={
                    "user_id": user_id,
                    "session_id": session_id,
                    "messages": messages,
                },
            )
        match_result = _expect_status(response, 200)
        if match_result.get("analysis") != ANALYSIS:
            raise RuntimeError("POST /match analysis does not match the stub")
        if match_result.get("match") != MATCH:
            raise RuntimeError("POST /match result does not match the stub")
        if match_result.get("profile_updated") is not True:
            raise RuntimeError("POST /match did not update the profile")
        matched_session = verification_storage.load_session(session_id)
        if matched_session.metadata.get("session_status") != "matched":
            raise RuntimeError("POST /match did not update the Drive session")
        output("[OK] POST /match")

        profile_before_end = verification_storage.load_profile(user_id)
        if profile_before_end.get("user_id") != user_id:
            raise RuntimeError("persisted profile user_id does not match")
        if not profile_before_end.get("values"):
            raise RuntimeError("persisted profile has no live test content")
        output("[OK] profile persisted to Google Drive")

        stage = "POST /sessions/{session_id}/end"
        response = client.post(
            f"/sessions/{session_id}/end",
            json={
                "user_id": user_id,
                "messages": messages,
                "analysis": match_result["analysis"],
                "match": match_result["match"],
                "top_candidates": match_result["top_candidates"],
                "after_match_support": match_result["after_match_support"],
            },
        )
        end_result = _expect_status(response, 200)
        if end_result != {"status": "completed"}:
            raise RuntimeError("session end response is invalid")
        output("[OK] POST /sessions/{session_id}/end")

        completed_session = verification_storage.load_session(session_id)
        if completed_session.metadata.get("session_status") != "completed":
            raise RuntimeError("Drive session is not completed")
        if completed_session.metadata.get("end_reason") != "user_clicked_finish":
            raise RuntimeError("Drive session end_reason is invalid")
        if completed_session.metadata.get("session_id") != session_id:
            raise RuntimeError("Drive session_id does not match")
        if verification_storage.load_profile(user_id) != profile_before_end:
            raise RuntimeError("session end unexpectedly changed the profile")
        output("[OK] session completed in Google Drive")
    except LiveApiTestFailure:
        raise
    except Exception as exc:
        raise LiveApiTestFailure(stage, exc) from exc

    output("FastAPI + Google Drive live integration test succeeded.")
    output(f"Test user ID: {user_id}")
    output(f"Test session ID: {session_id}")
    return LiveApiTestResult(user_id=user_id, session_id=session_id)


def _storage_from_env() -> GoogleDriveStorage:
    if os.getenv("FAIRIES_STORAGE_BACKEND", "").strip().lower() != "google_drive":
        raise StorageConfigurationError(
            "FAIRIES_STORAGE_BACKEND must be google_drive for the live test"
        )
    if os.getenv("GOOGLE_DRIVE_AUTH_MODE", "").strip().lower() != "user_oauth":
        raise StorageConfigurationError(
            "GOOGLE_DRIVE_AUTH_MODE must be user_oauth for the live test"
        )
    if not os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "").strip():
        raise StorageConfigurationError(
            "GOOGLE_DRIVE_ROOT_FOLDER_ID is not configured"
        )
    return GoogleDriveStorage.from_env()


def main() -> int:
    verification_storage = _storage_from_env()
    with TestClient(app) as client:
        run_live_integration_test(client, verification_storage)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LiveApiTestFailure, StorageError) as exc:
        print(f"[FAILED] {exc}", file=sys.stderr)
        raise SystemExit(1)
