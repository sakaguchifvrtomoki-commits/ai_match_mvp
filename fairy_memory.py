"""
Fairy profile-aware memory context functions for conversation generation.
"""
from typing import Optional


def build_fairy_memory_context(profile: dict) -> tuple[str, list[str]]:
    """
    Generate memory context for conversation from profile.
    Returns: (context_text, used_fields_list)
    - context_text: up to 500 characters
    - used_fields_list: field names actually used from profile
    """
    if not isinstance(profile, dict):
        return "", []

    used_fields = []
    parts = []

    summary = profile.get("summary", {})
    if isinstance(summary, dict):
        recent = (summary.get("recent") or "").strip()
        stable = (summary.get("stable") or "").strip()
        summary_text = recent or stable
        if summary_text:
            if len(summary_text) > 100:
                summary_text = summary_text[:100] + "..."
            parts.append(f"ユーザーの特徴: {summary_text}")
            if recent:
                used_fields.append("summary.recent")
            elif stable:
                used_fields.append("summary.stable")

    personality = profile.get("personality_traits", {})
    if isinstance(personality, dict):
        traits = []
        for key in ["communication_style", "decision_style", "emotional_tendency"]:
            val = (personality.get(key) or "").strip()
            if val and len(val) > 50:
                val = val[:50] + "..."
            if val:
                traits.append(val)
                used_fields.append(f"personality_traits.{key}")
        if traits:
            parts.append(f"性格傾向: {' / '.join(traits)}")

    values = profile.get("values", [])
    if isinstance(values, list) and values:
        value_list = [v.strip() for v in values[:3] if v]
        if value_list:
            parts.append(f"大切にしていること: {' / '.join(value_list)}")
            used_fields.append("values")

    preferences = profile.get("preferences", {})
    if isinstance(preferences, dict):
        rel_style = (preferences.get("relationship_style") or "").strip()
        if rel_style:
            if len(rel_style) > 50:
                rel_style = rel_style[:50] + "..."
            parts.append(f"関係スタイル: {rel_style}")
            used_fields.append("preferences.relationship_style")

        topics = preferences.get("conversation_topics", [])
        if isinstance(topics, list) and topics:
            topic_list = [t.strip() for t in topics[:5] if t]
            if topic_list:
                parts.append(f"好む話題: {' / '.join(topic_list[:3])}")
                used_fields.append("preferences.conversation_topics")

    mh = profile.get("matching_hypothesis", {})
    if isinstance(mh, dict):
        good_match = (mh.get("recent_good_match") or mh.get("stable_good_match") or "").strip()
        if good_match:
            if len(good_match) > 80:
                good_match = good_match[:80] + "..."
            parts.append(f"合いそうなタイプ: {good_match}")
            if mh.get("recent_good_match"):
                used_fields.append("matching_hypothesis.recent_good_match")
            else:
                used_fields.append("matching_hypothesis.stable_good_match")

    context = " / ".join(parts)
    if len(context) > 500:
        context = context[:500] + "..."

    return context, used_fields


def categorize_profile_interests(profile: dict) -> str:
    """
    Categorize user interest from profile.
    Returns: 'cultural', 'academic', 'casual', 'other'
    """
    if not isinstance(profile, dict):
        return "other"

    topics = profile.get("preferences", {}).get("conversation_topics", [])
    values = profile.get("values", [])
    summary = profile.get("summary", {})

    if isinstance(summary, dict):
        summary_text = (summary.get("recent") or summary.get("stable") or "").lower()
    else:
        summary_text = ""

    all_text = (" ".join(topics or []) + " " + " ".join(values or []) + " " + summary_text).lower()

    cultural_keywords = ["アニメ", "漫画", "映画", "ドラマ", "動画", "音楽", "作品", "本", "小説", "文化", "芸術"]
    academic_keywords = ["勉強", "学習", "数学", "科学", "統計", "プログラミング", "技術", "理論", "研究", "思考"]
    casual_keywords = ["食べ物", "外出", "旅行", "日常", "友達", "人間関係", "遊び", "リラックス"]

    cultural_count = sum(1 for kw in cultural_keywords if kw in all_text)
    academic_count = sum(1 for kw in academic_keywords if kw in all_text)
    casual_count = sum(1 for kw in casual_keywords if kw in all_text)

    if cultural_count >= academic_count and cultural_count >= casual_count and cultural_count > 0:
        return "cultural"
    if academic_count >= casual_count and academic_count > 0:
        return "academic"
    if casual_count > 0:
        return "casual"
    return "other"
