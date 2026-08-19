import json

import pytest
from fastapi.testclient import TestClient

from api import session_end_service
from api.main import app


client = TestClient(app)
SESSION_ID = "session_20260819_120000_abcdef"
BODY = {"user_id": "user_test", "messages": [{"role": "user", "content": "終了します"}],
        "analysis": None, "match": None, "top_candidates": [], "after_match_support": None}


@pytest.fixture
def session_files(monkeypatch, tmp_path):
    monkeypatch.setattr(session_end_service.streamlit_app, "__file__", str(tmp_path / "app.py"))
    base = tmp_path / "logs" / "0.2.2" / "sessions"
    base.mkdir(parents=True)
    log = base / "session_20260819_120000_v0.2.2_abcdef.md"
    meta = log.with_suffix(".json")
    log.write_text("started", encoding="utf-8")
    meta.write_text(json.dumps({"session_id": SESSION_ID, "user_id": "user_test",
        "started_at": "2026-08-19T12:00:00+09:00", "consented_at": "2026-08-19T12:00:00+09:00",
        "log_consent": True, "session_status": "started", "log_path": str(log)}), encoding="utf-8")
    return log, meta


def test_end_session_saves_completed_fields(session_files):
    log, meta = session_files
    response = client.post(f"/sessions/{SESSION_ID}/end", json=BODY)
    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    text = log.read_text(encoding="utf-8")
    assert "- session_status: completed" in text
    assert "- end_reason: user_clicked_finish" in text
    assert "- ended_at: " in text and "- ended_at: \n" not in text
    data = json.loads(meta.read_text(encoding="utf-8"))
    assert data["session_status"] == "completed"
    assert data["end_reason"] == "user_clicked_finish"
    assert data["ended_at"]


def test_invalid_session_id():
    response = client.post("/sessions/invalid/end", json=BODY)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("missing", ["user_id", "messages"])
def test_missing_required_request_field(missing):
    body = dict(BODY)
    body.pop(missing)
    response = client.post(f"/sessions/{SESSION_ID}/end", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_log_failure_returns_retryable_error(monkeypatch):
    monkeypatch.setattr(session_end_service, "_find_session_files",
                        lambda session_id: (_ for _ in ()).throw(session_end_service.SessionEndFailed("保存失敗")))
    response = client.post(f"/sessions/{SESSION_ID}/end", json=BODY)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "SESSION_END_FAILED"


def test_end_does_not_run_ai_matching_or_profile_update(monkeypatch, session_files):
    import api.match_service as match_service
    monkeypatch.setattr(match_service, "analyze_user", lambda *a: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(match_service, "generate_match", lambda *a: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(match_service, "update_fairy_profile", lambda *a: (_ for _ in ()).throw(AssertionError()))
    assert client.post(f"/sessions/{SESSION_ID}/end", json=BODY).status_code == 200


def test_existing_endpoints_remain_available():
    paths = {route.path for route in app.routes}
    assert {"/sessions", "/chat", "/match", "/sessions/{session_id}/end"} <= paths
