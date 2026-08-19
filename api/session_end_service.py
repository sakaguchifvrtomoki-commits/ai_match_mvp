import datetime
import json
from pathlib import Path

import app as streamlit_app
from api.chat_service import validate_chat_identifiers


class SessionEndFailed(RuntimeError):
    pass


def _find_session_files(session_id: str) -> tuple[Path, Path]:
    base = Path(streamlit_app.__file__).parent / "logs" / "0.2.2" / "sessions"
    suffix = session_id.rsplit("_", 1)[-1]
    metadata = list(base.glob(f"*{suffix}.json"))
    if len(metadata) != 1:
        raise SessionEndFailed("終了対象のセッション情報が見つかりません。")
    try:
        data = json.loads(metadata[0].read_text(encoding="utf-8"))
        log_path = Path(data["log_path"])
    except Exception as exc:
        raise SessionEndFailed("セッション情報を読み込めませんでした。") from exc
    return metadata[0], log_path


def end_session(session_id: str, payload: dict) -> None:
    validate_chat_identifiers(payload["user_id"], session_id)
    metadata_path, log_path = _find_session_files(session_id)
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SessionEndFailed("セッション情報を読み込めませんでした。") from exc
    if metadata.get("session_id") != session_id or metadata.get("user_id") != payload["user_id"]:
        raise SessionEndFailed("セッション情報が一致しません。")

    ended_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "# AI分身マッチングMVP ログ", "", "## セッション情報",
        "- app_version: v0.2.2", f"- session_id: {session_id}",
        f"- user_id: {payload['user_id']}", f"- started_at: {metadata.get('started_at', '')}",
        f"- ended_at: {ended_at}", f"- log_consent: {str(metadata.get('log_consent', '')).lower()}",
        f"- consented_at: {metadata.get('consented_at', '')}", "- session_status: completed",
        "- end_reason: user_clicked_finish", "", "## チャット履歴",
    ]
    lines += [f"[{m['role']}]: {m['content']}" for m in payload["messages"]]
    analysis = payload.get("analysis")
    if analysis:
        lines += ["", "## 分析結果",
                  f"性格傾向: {analysis['personality']}", f"価値観: {analysis['values']}",
                  f"隠れた欲求: {analysis['hidden_needs']}", f"会話スタイル: {analysis['communication_style']}",
                  f"理想の相手像: {analysis['ideal_partner_type']}", f"一言要約: {analysis['summary']}"]
    match = payload.get("match")
    if match:
        c = match["matched_candidate"]
        lines += ["", "## マッチング結果", f"マッチ相手: {c['name']} ({c['age']}歳)",
                  f"説明: {c['description']}", f"相性タイプ: {match['match_label']}",
                  f"相性ポイント: {match['match_reason']}", f"注意点: {match['possible_concern']}",
                  f"最初のメッセージ: {match['recommended_first_message']}"]
    top = payload.get("top_candidates") or []
    if len(top) > 1:
        lines += ["", "## 他にも相性が近かった候補者"]
        for index, item in enumerate(top[1:3], start=2):
            c = item["candidate"]
            reason = streamlit_app.generate_short_candidate_reason(analysis or {}, c)
            lines.append(f"{index}位: {c['name']} ({c['age']}歳) — {reason}")
    support = payload.get("after_match_support")
    if support:
        lines += ["", "## マッチ後支援", f"今日送る一言: {support['first_message_today']}",
                  f"3日以内に聞く質問: {support['question_in_3days']}",
                  f"避けたほうがいい一言: {support['avoid_phrase']}",
                  f"返信が遅いときの対応: {support['slow_reply_action']}"]
    try:
        log_path.write_text("\n".join(lines), encoding="utf-8")
        metadata.update(session_status="completed", end_reason="user_clicked_finish", ended_at=ended_at)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        raise SessionEndFailed("最終セッションログを保存できませんでした。") from exc
