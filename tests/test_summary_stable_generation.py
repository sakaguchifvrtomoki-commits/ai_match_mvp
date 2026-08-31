import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location("summary_app", Path(__file__).resolve().parents[1] / "app.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def candidate(key, description, status="candidate", support_count=1, session="s1"):
    return {
        "canonical_key": key,
        "description": description,
        "status": status,
        "support_count": support_count,
        "first_seen_session_id": session,
        "last_seen_session_id": session,
        "evidence": [session],
        "confidence": 0.7,
    }


def diff(summary=None, corrections=None):
    return {
        "summary": summary or {
            "stable_candidates": [],
            "reinforced_candidate_keys": [],
            "recent": "",
            "growth": "",
            "new_tensions": [],
        },
        "personality_traits_updates": {},
        "personality_trait_candidates": {
            "communication_style": [],
            "decision_style": [],
            "emotional_tendency": [],
        },
        "personality_trait_reinforced_keys": {
            "communication_style": [],
            "decision_style": [],
            "emotional_tendency": [],
        },
        "new_values": [],
        "preference_updates": {
            "relationship_style": "",
            "new_conversation_topics": [],
            "new_dislikes": [],
        },
        "matching_hypothesis_updates": {
            "stable_good_match_candidates": [],
            "reinforced_stable_good_match_candidate_keys": [],
            "recent_good_match": "",
            "likely_bad_match": "",
            "new_reasons": [],
        },
        "corrections": corrections or [],
        "confidence": {"summary": 0.8, "values": 0.0, "matching_hypothesis": 0.0},
    }


def test_one_stable_candidate_uses_natural_summary_generator():
    existing = mod._empty_profile("u_one")
    existing["summary"]["stable_candidates"] = [candidate("a", "思い出を大切にする")]
    existing["evidence"] = ["s1"]
    received = []

    merged = mod.merge_user_profiles(
        existing,
        diff({
            "stable_candidates": [],
            "reinforced_candidate_keys": ["a"],
            "recent": "",
            "growth": "",
            "new_tensions": [],
        }),
        "s2",
        summary_generator=lambda material: received.extend(material) or "過去の経験や思い出を大切にする傾向がある。",
    )

    assert merged["summary"]["stable"] == "過去の経験や思い出を大切にする傾向がある。"
    assert received == [{"status": "stable", "description": "思い出を大切にする"}]


def test_multiple_stable_candidates_are_sent_to_generator_not_joined():
    existing = mod._empty_profile("u_many")
    existing["summary"]["stable_candidates"] = [candidate("a", "思い出を大切にする"), candidate("b", "美しさに関心がある")]
    existing["evidence"] = ["s1"]
    calls = []

    merged = mod.merge_user_profiles(
        existing,
        diff({
            "stable_candidates": [],
            "reinforced_candidate_keys": ["a", "b"],
            "recent": "",
            "growth": "",
            "new_tensions": [],
        }),
        "s2",
        summary_generator=lambda material: calls.append(material) or "思い出への愛着があり、美しいものにも関心を持つ。",
    )

    assert len(calls) == 1
    assert {item["description"] for item in calls[0]} == {"思い出を大切にする", "美しさに関心がある"}
    assert merged["summary"]["stable"] == "思い出への愛着があり、美しいものにも関心を持つ。"


def test_explicit_correction_and_stable_candidates_are_all_material():
    existing = mod._empty_profile("u_correction")
    existing["summary"]["stable"] = "古い人物像"
    existing["summary"]["stable_candidates"] = [
        candidate("memory", "思い出を大切にする", "stable", 2),
        candidate("beauty", "美しいものに関心がある", "stable", 2),
        candidate("old", "古い時間観", "stable", 2),
        candidate("pending", "未確定の特徴"),
        candidate("past", "訂正済みの特徴", "corrected"),
    ]
    existing["evidence"] = ["s1"]
    calls = []

    merged = mod.merge_user_profiles(
        existing,
        diff(corrections=[{
            "field": "summary.stable",
            "target_canonical_key": "old",
            "old_value": "古い時間観",
            "new_canonical_key": "time",
            "new_value": "体内時間と物理時間を分けて考える",
            "reason": "明示的訂正",
        }]),
        "s2",
        summary_generator=lambda material: calls.append(material) or "思い出や美しさを大切にし、時間の基準も丁寧に整理して考える。",
    )

    assert {item["status"] for item in calls[0]} == {"stable", "explicit_correction"}
    assert {item["description"] for item in calls[0]} == {
        "思い出を大切にする", "美しいものに関心がある", "体内時間と物理時間を分けて考える",
    }
    assert merged["summary"]["stable"] != "体内時間と物理時間を分けて考える"
    assert any(item["status"] == "corrected" for item in merged["summary"]["stable_candidates"])


@pytest.mark.parametrize("summary_update", [
    {"stable_candidates": [], "reinforced_candidate_keys": [], "recent": "最近の話", "growth": "", "new_tensions": []},
    {"stable_candidates": [], "reinforced_candidate_keys": [], "recent": "", "growth": "最近の成長", "new_tensions": []},
    {"stable_candidates": [{"canonical_key": "new", "description": "まだ未確定"}], "reinforced_candidate_keys": [], "recent": "", "growth": "", "new_tensions": []},
])
def test_non_stable_changes_do_not_call_summary_generator(summary_update):
    existing = mod._empty_profile("u_unchanged")
    existing["summary"]["stable"] = "確立済みの人物像。"
    existing["summary"]["stable_candidates"] = [candidate("stable", "確立済み特徴", "stable", 2)]
    existing["evidence"] = ["s1"]
    calls = []

    merged = mod.merge_user_profiles(
        existing, diff(summary_update), "s2", summary_generator=lambda material: calls.append(material) or "呼ばれない",
    )

    assert calls == []
    assert merged["summary"]["stable"] == "確立済みの人物像。"


def test_ai_summary_failure_preserves_existing_stable_and_profile_update():
    existing = mod._empty_profile("u_failure")
    existing["summary"]["stable"] = "既存の自然な人物像。"
    existing["summary"]["stable_candidates"] = [
        candidate("old", "既存の確定特徴", "stable", 2),
        candidate("new", "新しく確定する特徴"),
    ]
    existing["evidence"] = ["s1"]

    merged = mod.merge_user_profiles(
        existing,
        diff({
            "stable_candidates": [],
            "reinforced_candidate_keys": ["new"],
            "recent": "更新されたrecent",
            "growth": "",
            "new_tensions": [],
        }),
        "s2",
        summary_generator=lambda material: None,
    )

    assert merged["summary"]["stable"] == "既存の自然な人物像。"
    assert merged["summary"]["recent"] == "更新されたrecent"
    assert next(c for c in merged["summary"]["stable_candidates"] if c["canonical_key"] == "new")["status"] == "stable"


def test_existing_explicit_correction_regression_is_not_permanently_solo():
    existing = mod._empty_profile("u_regression")
    existing["summary"]["stable"] = "体内時間と物理時間を別物として切り分けて考える"
    existing["summary"]["stable_candidates"] = [
        candidate("memory", "昔の写真や動画を見返して懐かしさを感じる", "stable", 3),
        candidate("figure", "フィギュアをきれいで美しいものとして捉えている", "stable", 3),
        candidate("plant", "植物を育てることに関心がある", "stable", 2),
        candidate("event", "イベントの雰囲気や思い出を大切にする", "stable", 3),
        candidate("time", "体内時間と物理時間を別物として切り分けて考える", "explicit_correction", 1),
        candidate("action", "日々の行動を積み重ねる", "candidate", 1),
    ]
    existing["evidence"] = ["s1"]
    received = []

    merged = mod.merge_user_profiles(
        existing,
        diff({
            "stable_candidates": [],
            "reinforced_candidate_keys": ["action"],
            "recent": "",
            "growth": "",
            "new_tensions": [],
        }),
        "s2",
        summary_generator=lambda material: received.extend(material) or "思い出や美しさを大切にし、物事の基準を整理しながら日々の行動も積み重ねる。",
    )

    assert len(received) == 6
    assert {item["status"] for item in received} == {"stable", "explicit_correction"}
    assert merged["summary"]["stable"] != "体内時間と物理時間を別物として切り分けて考える"


def test_generate_stable_summary_prompt_contains_only_confirmed_material(monkeypatch):
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="確定情報だけを統合した自然な人物像。"),
            )])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr(mod, "get_openai_client", lambda: fake_client)

    result = mod.generate_stable_summary([
        {"status": "stable", "description": "確定特徴"},
        {"status": "explicit_correction", "description": "明示訂正"},
        {"status": "candidate", "description": "未確定特徴"},
        {"status": "corrected", "description": "訂正済み特徴"},
    ])

    prompt = captured["messages"][1]["content"]
    assert result == "確定情報だけを統合した自然な人物像。"
    assert "確定特徴" in prompt and "明示訂正" in prompt
    assert "未確定特徴" not in prompt and "訂正済み特徴" not in prompt
    assert captured["max_completion_tokens"] == 700
