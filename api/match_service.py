import datetime
import json
from dataclasses import dataclass

import app as streamlit_app
from api.chat_service import load_user_profile, validate_chat_identifiers
from api.storage import get_storage


class InsufficientMessages(ValueError):
    pass


class AnalysisFailed(RuntimeError):
    pass


class MatchingFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class MatchOutcome:
    analysis: dict
    match: dict
    top_candidates: list[dict]
    after_match_support: dict | None
    profile_updated: bool


def analyze_user(messages: list[dict], user_id: str) -> dict:
    client = streamlit_app.get_openai_client()
    if client is None:
        raise AnalysisFailed
    conversation = "\n".join(f"[{m['role']}]: {m['content']}" for m in messages)
    profile_hint = ""
    try:
        existing = load_user_profile(user_id)
        summary = streamlit_app.get_profile_summary_display(existing)
        if summary:
            profile_hint = (
                "\n\n【Fairyの記憶（補助情報。今回の会話を最優先し、参考程度に使用してください）】\n"
                f"これまでの印象: {summary}\n"
            )
            values = existing.get("values", [])
            if values:
                profile_hint += f"大切にしていること: {', '.join(values)}\n"
    except Exception:
        profile_hint = ""
    prompt = (
        "あなたはユーザーの性格、価値観、本音を分析するアシスタントです。"
        " 以下の会話履歴から、JSON形式で分析結果を出力してください。\n\n"
        "【出力形式】\n以下の6つのキーを持つJSONオブジェクトのみを出力してください。\n"
        '{"personality":"性格傾向","values":"価値観","hidden_needs":"隠れた欲求",'
        '"communication_style":"会話スタイル","ideal_partner_type":"相性が良い相手像","summary":"一言要約"}\n\n'
        "【制約】JSONのみを出力し、各値は必ず空でない文字列にしてください。今回の会話を保存プロフィールより優先してください。\n\n"
        f"会話履歴:\n{conversation}{profile_hint}\n"
    )
    try:
        response = client.chat.completions.create(
            model=streamlit_app.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "日本語で分析し、有効なJSONのみを返してください。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_completion_tokens=1200,
            response_format={"type": "json_object"},
        )
        analysis = streamlit_app.extract_json(response.choices[0].message.content.strip())
        valid, _ = streamlit_app.validate_analysis_result(analysis)
        if not valid:
            raise AnalysisFailed
        return analysis
    except AnalysisFailed:
        raise
    except Exception as exc:
        raise AnalysisFailed from exc


def generate_match(analysis: dict, candidates: list[dict]) -> tuple[dict, list[dict]]:
    try:
        top = streamlit_app.choose_top_candidates(analysis, candidates, top_n=3)
    except Exception as exc:
        raise MatchingFailed from exc
    if not top:
        raise MatchingFailed
    best = top[0]
    details = generate_match_details(analysis, best["candidate"])
    if details is None:
        raise MatchingFailed
    result = {
        "matched_candidate": best["candidate"],
        "match_score": min(max(int(best["similarity"] * 100), 0), 100),
        "match_label": streamlit_app.assign_match_type(analysis, best["candidate"]),
        "match_reason": details["reason"],
        "possible_concern": details["caution"],
        "recommended_first_message": details["first_message"],
    }
    return result, top


def generate_match_details(analysis: dict, candidate: dict) -> dict | None:
    client = streamlit_app.get_openai_client()
    if client is None:
        return None
    prompt = streamlit_app.build_match_details_prompt(analysis, candidate)
    for _ in range(3):
        try:
            response = client.chat.completions.create(
                model=streamlit_app.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "日本語で具体的なマッチング情報をJSONのみで返してください。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_completion_tokens=2000,
            )
            details = streamlit_app.extract_json(response.choices[0].message.content.strip())
            valid, _ = streamlit_app.validate_match_details(details)
            if valid:
                return details
        except Exception:
            continue
    return None


def generate_after_match_support(analysis: dict, match: dict) -> dict | None:
    client = streamlit_app.get_openai_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=streamlit_app.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "日本語で丁寧に回答し、JSON形式で出力してください。"},
                {"role": "user", "content": streamlit_app.build_after_match_support_prompt(analysis, match)},
            ],
            temperature=0.8,
            max_completion_tokens=2500,
        )
        support = streamlit_app.extract_json(response.choices[0].message.content.strip())
        required = {"first_message_today", "question_in_3days", "avoid_phrase", "slow_reply_action"}
        return support if isinstance(support, dict) and required <= support.keys() else None
    except Exception:
        return None


def update_fairy_profile(user_id: str, messages: list[dict], session_id: str) -> bool:
    try:
        existing = load_user_profile(user_id)
    except Exception:
        return False
    if session_id in (existing.get("evidence") or []):
        return True
    try:
        get_storage().save_profile_history(user_id, session_id, existing, "before")
    except Exception:
        # Match v0.2.1: a history-copy failure does not overwrite or abort the profile.
        pass
    client = streamlit_app.get_openai_client()
    template = streamlit_app.load_profile_extraction_prompt()
    if client is None or not template:
        return False
    conversation = "\n".join(f"[{m['role']}]: {m['content']}" for m in messages)
    base_prompt = (
        template.replace("{{CONVERSATION}}", conversation)
        .replace("{{EXISTING_PROFILE}}", json.dumps(existing, ensure_ascii=False, indent=2))
        .replace("{{USER_ID}}", user_id)
        .replace("{{SESSION_ID}}", session_id)
    )
    diff = None
    for attempt in range(2):
        try:
            prompt = base_prompt + ("\n前回の出力が不正でした。短い差分JSONのみ返してください。" if attempt else "")
            response = client.chat.completions.create(
                model=streamlit_app.OPENAI_MODEL,
                messages=[{"role": "system", "content": "有効なプロフィール差分JSONのみ返してください。"}, {"role": "user", "content": prompt}],
                temperature=0.3,
                max_completion_tokens=5000,
                response_format={"type": "json_object"},
            )
            diff = streamlit_app.extract_json(response.choices[0].message.content.strip())
            if isinstance(diff, dict):
                break
        except Exception:
            pass
    if not isinstance(diff, dict):
        return False
    diff.update(user_id=user_id, profile_version=streamlit_app.CURRENT_PROFILE_VERSION,
                updated_at=datetime.datetime.now().isoformat(timespec="seconds"))
    try:
        merged = streamlit_app.merge_user_profiles(existing, diff, session_id)
        streamlit_app.validate_profile(merged)
        storage = get_storage()
        storage.save_profile(user_id, merged)
        storage.save_profile_history(user_id, session_id, merged, "after")
        return True
    except Exception:
        return False


def save_session_log(user_id: str, session_id: str, messages: list[dict], analysis: dict,
                     match: dict, top: list[dict], support: dict | None) -> bool:
    candidate = match["matched_candidate"]
    lines = ["# AI分身マッチングMVP ログ", "", "## セッション情報",
             "- app_version: v0.2.2", f"- session_id: {session_id}", f"- user_id: {user_id}",
             "- session_status: matched", "", "## チャット履歴"]
    lines += [f"[{m['role']}]: {m['content']}" for m in messages]
    lines += ["", "## 分析結果"] + [f"{k}: {v}" for k, v in analysis.items()]
    lines += ["", "## マッチング結果", f"マッチ相手: {candidate['name']} ({candidate['age']}歳)",
              f"相性タイプ: {match['match_label']}", f"相性ポイント: {match['match_reason']}",
              f"注意点: {match['possible_concern']}", f"最初のメッセージ: {match['recommended_first_message']}"]
    if support:
        lines += ["", "## マッチ後支援"] + [f"{k}: {v}" for k, v in support.items()]
    try:
        get_storage().update_session(session_id, {"session_status": "matched"}, "\n".join(lines))
        return True
    except Exception:
        return False


def run_match(user_id: str, session_id: str, messages: list[dict]) -> MatchOutcome:
    validate_chat_identifiers(user_id, session_id)
    if sum(1 for m in messages if m["role"] == "user" and m["content"].strip()) < 3:
        raise InsufficientMessages
    analysis = analyze_user(messages, user_id)
    try:
        candidates = streamlit_app.load_candidates()
    except Exception as exc:
        raise MatchingFailed from exc
    match, top = generate_match(analysis, candidates)
    support = generate_after_match_support(analysis, match)
    updated = update_fairy_profile(user_id, messages, session_id)
    save_session_log(user_id, session_id, messages, analysis, match, top, support)
    return MatchOutcome(analysis, match, top, support, updated)
