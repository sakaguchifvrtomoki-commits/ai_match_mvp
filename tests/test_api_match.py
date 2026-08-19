from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import match_service
from api.main import app


client = TestClient(app)
MESSAGES = [
    {"role": "assistant", "content": "こんにちは"},
    {"role": "user", "content": "本が好きです"},
    {"role": "assistant", "content": "どんな本ですか"},
    {"role": "user", "content": "小説です"},
    {"role": "assistant", "content": "何を大切にしますか"},
    {"role": "user", "content": "信頼です"},
]
REQUEST = {"user_id": "user_test", "session_id": "session_20260819_120000_abcdef", "messages": MESSAGES}
ANALYSIS = {"personality": "穏やか", "values": "信頼", "hidden_needs": "安心", "communication_style": "丁寧", "ideal_partner_type": "誠実", "summary": "信頼を重視"}
CANDIDATE = {"id": "c01", "name": "葵", "age": 29, "personality": "穏やか", "values": "信頼", "hobbies": "読書", "communication_style": "丁寧", "relationship_style": "じっくり", "description": "誠実な人"}
MATCH = {"matched_candidate": CANDIDATE, "match_score": 90, "match_label": "安心感重視タイプ", "match_reason": "理由", "possible_concern": "注意", "recommended_first_message": "こんにちは"}
TOP = [{"candidate": CANDIDATE, "similarity": 0.9}]
SUPPORT = {"first_message_today": "今日", "question_in_3days": "質問", "avoid_phrase": "避ける", "slow_reply_action": "待つ"}


def install_pipeline(monkeypatch, support=SUPPORT, updated=True):
    monkeypatch.setattr(match_service, "analyze_user", lambda messages, user_id: ANALYSIS)
    monkeypatch.setattr(match_service.streamlit_app, "load_candidates", lambda: [CANDIDATE])
    monkeypatch.setattr(match_service, "generate_match", lambda analysis, candidates: (MATCH, TOP))
    monkeypatch.setattr(match_service, "generate_after_match_support", lambda analysis, match: support)
    monkeypatch.setattr(match_service, "update_fairy_profile", lambda *args: updated)
    monkeypatch.setattr(match_service, "save_session_log", lambda *args: True)


def test_match_success_returns_v021_structures(monkeypatch):
    install_pipeline(monkeypatch)
    response = client.post("/match", json=REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body == {"analysis": ANALYSIS, "match": MATCH, "top_candidates": TOP,
                    "after_match_support": SUPPORT, "profile_updated": True}


def test_less_than_three_user_messages(monkeypatch):
    called = False
    monkeypatch.setattr(match_service, "analyze_user", lambda *args: (_ for _ in ()).throw(AssertionError()))
    body = {**REQUEST, "messages": MESSAGES[:4]}
    response = client.post("/match", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INSUFFICIENT_MESSAGES"


def test_analysis_failure_stops_matching(monkeypatch):
    monkeypatch.setattr(match_service, "analyze_user", lambda *args: (_ for _ in ()).throw(match_service.AnalysisFailed()))
    monkeypatch.setattr(match_service, "generate_match", lambda *args: (_ for _ in ()).throw(AssertionError()))
    response = client.post("/match", json=REQUEST)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ANALYSIS_FAILED"


def test_matching_failure(monkeypatch):
    monkeypatch.setattr(match_service, "analyze_user", lambda *args: ANALYSIS)
    monkeypatch.setattr(match_service.streamlit_app, "load_candidates", lambda: [CANDIDATE])
    monkeypatch.setattr(match_service, "generate_match", lambda *args: (_ for _ in ()).throw(match_service.MatchingFailed()))
    response = client.post("/match", json=REQUEST)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MATCHING_FAILED"


def test_support_failure_is_partial_success(monkeypatch):
    install_pipeline(monkeypatch, support=None)
    response = client.post("/match", json=REQUEST)
    assert response.status_code == 200
    assert response.json()["after_match_support"] is None
    assert response.json()["match"] == MATCH


def test_profile_failure_is_partial_success(monkeypatch):
    install_pipeline(monkeypatch, updated=False)
    response = client.post("/match", json=REQUEST)
    assert response.status_code == 200
    assert response.json()["profile_updated"] is False


def test_profile_load_failure_never_saves_empty_profile(monkeypatch):
    monkeypatch.setattr(match_service, "load_user_profile", lambda user_id: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(match_service.streamlit_app, "atomic_save_profile", lambda *args: (_ for _ in ()).throw(AssertionError()))
    assert match_service.update_fairy_profile("user_test", MESSAGES, REQUEST["session_id"]) is False


def test_duplicate_session_profile_update_is_idempotent(monkeypatch):
    profile = {"evidence": [REQUEST["session_id"]]}
    monkeypatch.setattr(match_service, "load_user_profile", lambda user_id: profile)
    monkeypatch.setattr(match_service.streamlit_app, "get_openai_client", lambda: (_ for _ in ()).throw(AssertionError()))
    assert match_service.update_fairy_profile("user_test", MESSAGES, REQUEST["session_id"]) is True


def test_session_log_is_saved_after_profile_update(monkeypatch):
    order = []
    install_pipeline(monkeypatch)
    monkeypatch.setattr(match_service, "update_fairy_profile", lambda *args: order.append("profile") or True)
    monkeypatch.setattr(match_service, "save_session_log", lambda *args: order.append("log") or True)
    response = client.post("/match", json=REQUEST)
    assert response.status_code == 200
    assert order == ["profile", "log"]


def test_end_endpoint_is_still_unimplemented():
    assert "/sessions/{session_id}/end" not in {route.path for route in app.routes}
