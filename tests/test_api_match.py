from types import SimpleNamespace
import json

import pytest
from fastapi.testclient import TestClient

from api import match_service
from api.main import app
from api.storage.base import Unavailable


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
    monkeypatch.setattr(match_service, "load_fairy_profile_summary", lambda *args: None)
    monkeypatch.setattr(match_service, "save_session_log", lambda *args: True)


def test_match_success_returns_v021_structures(monkeypatch):
    install_pipeline(monkeypatch)
    response = client.post("/match", json=REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body == {"analysis": ANALYSIS, "match": MATCH, "top_candidates": TOP,
                    "after_match_support": SUPPORT, "profile_updated": True,
                    "fairy_profile_summary": None}


def _stream_events(response):
    return [json.loads(line) for line in response.text.splitlines() if line]


def test_match_stream_returns_real_phases_and_result(monkeypatch):
    install_pipeline(monkeypatch)

    response = client.post("/match/stream", json=REQUEST)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-cache"
    events = _stream_events(response)
    assert [event["type"] for event in events] == [
        "progress", "progress", "progress", "result"
    ]
    assert [event["phase"] for event in events[:-1]] == [
        "analyzing", "matching", "memorizing"
    ]
    assert events[-1]["data"] == client.post("/match", json=REQUEST).json()
    assert len(response.text.splitlines()) == 4


def test_match_stream_analysis_failure_is_terminal_error(monkeypatch):
    monkeypatch.setattr(
        match_service,
        "analyze_user",
        lambda *args: (_ for _ in ()).throw(match_service.AnalysisFailed()),
    )

    response = client.post("/match/stream", json=REQUEST)

    events = _stream_events(response)
    assert events == [
        {"type": "progress", "phase": "analyzing"},
        {
            "type": "error",
            "error": {
                "code": "ANALYSIS_FAILED",
                "message": "人物分析に失敗しました。再試行してください。",
            },
        },
    ]


@pytest.mark.parametrize(
    ("support", "updated"),
    [(None, True), (SUPPORT, False)],
)
def test_match_stream_partial_failures_still_return_result(
    monkeypatch, support, updated
):
    install_pipeline(monkeypatch, support=support, updated=updated)

    events = _stream_events(client.post("/match/stream", json=REQUEST))

    assert events[-1]["type"] == "result"
    assert not any(event["type"] == "error" for event in events)
    assert events[-1]["data"]["after_match_support"] == support
    assert events[-1]["data"]["profile_updated"] is updated


def test_match_stream_business_validation_stays_http_error(monkeypatch):
    monkeypatch.setattr(
        match_service,
        "analyze_user",
        lambda *args: (_ for _ in ()).throw(AssertionError()),
    )
    body = {**REQUEST, "messages": MESSAGES[:4]}

    response = client.post("/match/stream", json=body)

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "INSUFFICIENT_MESSAGES"


def test_profile_summary_uses_legacy_display_rules_and_limits_values(monkeypatch):
    profile = {
        "summary": {"stable": "長期的な理解", "recent": "最近の関心", "growth": "変化の兆し"},
        "values": ["信頼", "対話", "成長", "安心", "誠実", "6件目"],
        "preferences": {"relationship_style": "じっくり関係を築く"},
        "matching_hypothesis": {
            "recent_good_match": "最近合いそうな相手",
            "stable_good_match": "長期的に合う相手",
            "likely_good_match": "推定相手",
        },
    }
    monkeypatch.setattr(match_service, "load_user_profile", lambda _user_id: profile)

    summary = match_service.load_fairy_profile_summary("user_test")

    assert summary == {
        "understanding": "長期的な理解 / 最近: 最近の関心 / 変化: 変化の兆し",
        "values": ["信頼", "対話", "成長", "安心", "誠実"],
        "relationship_style": "じっくり関係を築く",
        "good_match": "最近合いそうな相手",
    }


def test_profile_summary_success_does_not_emit_diagnostic_info(monkeypatch):
    profile = {
        "summary": {"stable": "本文はログへ出さない", "recent": "", "growth": ""},
        "values": ["信頼", "対話"],
        "preferences": {"relationship_style": "じっくり"},
        "matching_hypothesis": {"recent_good_match": "誠実な相手"},
    }
    logs = []
    monkeypatch.setenv("FAIRIES_STORAGE_BACKEND", "google_drive")
    monkeypatch.setattr(match_service, "load_user_profile", lambda _user_id: profile)
    monkeypatch.setattr(
        match_service.logger,
        "info",
        lambda message, *args: logs.append(message % args),
    )

    summary = match_service.load_fairy_profile_summary("user_test")

    assert summary is not None
    assert logs == []


def test_profile_summary_failure_logs_diagnostics_and_returns_none(monkeypatch):
    warnings = []
    monkeypatch.setenv("FAIRIES_STORAGE_BACKEND", "google_drive")
    monkeypatch.setattr(
        match_service,
        "load_user_profile",
        lambda _user_id: (_ for _ in ()).throw(Unavailable("storage down")),
    )
    monkeypatch.setattr(
        match_service.logger,
        "warning",
        lambda message, *args: warnings.append(message % args),
    )

    summary = match_service.load_fairy_profile_summary("user_test")

    assert summary is None
    assert len(warnings) == 1
    assert "user_id=user_test" in warnings[0]
    assert "backend=google_drive" in warnings[0]
    assert "profile_loaded=false" in warnings[0]
    assert "exception=Unavailable" in warnings[0]
    assert "message=storage down" in warnings[0]


@pytest.mark.parametrize(
    ("matching_hypothesis", "expected"),
    [
        ({"recent_good_match": "recent", "stable_good_match": "stable", "likely_good_match": "likely"}, "recent"),
        ({"recent_good_match": "", "stable_good_match": "stable", "likely_good_match": "likely"}, "stable"),
        ({"recent_good_match": "", "stable_good_match": "", "likely_good_match": "likely"}, "likely"),
    ],
)
def test_profile_summary_preserves_legacy_good_match_priority(
    monkeypatch, matching_hypothesis, expected
):
    monkeypatch.setattr(match_service, "load_user_profile", lambda _user_id: {
        "summary": {}, "values": [], "preferences": {},
        "matching_hypothesis": matching_hypothesis,
    })

    assert match_service.load_fairy_profile_summary("user_test")["good_match"] == expected


def test_match_response_contains_existing_profile_summary(monkeypatch):
    install_pipeline(monkeypatch)
    summary = {"understanding": "既存の理解", "values": ["信頼"],
               "relationship_style": "じっくり", "good_match": "誠実な相手"}
    monkeypatch.setattr(match_service, "load_fairy_profile_summary", lambda _user_id: summary)

    response = client.post("/match", json=REQUEST)

    assert response.status_code == 200
    assert response.json()["fairy_profile_summary"] == summary


def test_profile_summary_is_returned_when_current_update_fails(monkeypatch):
    install_pipeline(monkeypatch, updated=False)
    summary = {"understanding": "既存の理解", "values": [],
               "relationship_style": "", "good_match": "誠実な相手"}
    monkeypatch.setattr(match_service, "load_fairy_profile_summary", lambda _user_id: summary)

    response = client.post("/match", json=REQUEST)

    assert response.status_code == 200
    assert response.json()["profile_updated"] is False
    assert response.json()["fairy_profile_summary"] == summary


def test_profile_summary_load_failure_keeps_match_successful(monkeypatch):
    summary_loader = match_service.load_fairy_profile_summary
    install_pipeline(monkeypatch)
    monkeypatch.setattr(match_service, "load_fairy_profile_summary", summary_loader)
    monkeypatch.setattr(
        match_service,
        "load_user_profile",
        lambda _user_id: (_ for _ in ()).throw(Unavailable("storage down")),
    )

    response = client.post("/match", json=REQUEST)

    assert response.status_code == 200
    assert response.json()["fairy_profile_summary"] is None


def test_profile_summary_does_not_call_openai(monkeypatch):
    monkeypatch.setattr(match_service, "load_user_profile", lambda _user_id: {
        "summary": {"stable": "確定済みの理解", "recent": "", "growth": ""},
        "values": [], "preferences": {}, "matching_hypothesis": {},
    })
    monkeypatch.setattr(
        match_service.streamlit_app,
        "get_openai_client",
        lambda: (_ for _ in ()).throw(AssertionError("OpenAI must not be called")),
    )

    assert match_service.load_fairy_profile_summary("user_test")["understanding"] == "確定済みの理解"


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
    assert "/sessions/{session_id}/end" in {route.path for route in app.routes}
