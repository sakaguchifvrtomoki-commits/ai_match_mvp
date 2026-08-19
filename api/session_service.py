import datetime
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import app as streamlit_app


API_VERSION = "0.2.2"
DEFAULT_DISPLAY_NAME = streamlit_app.DEFAULT_DISPLAY_NAME
INITIAL_GREETING_FALLBACK = "今日はどんな話から始めましょうか？"


class InvalidSessionRequest(ValueError):
    """The request cannot be used to start a session."""


class SessionStartError(RuntimeError):
    """A required session-start operation failed."""


@dataclass(frozen=True)
class StartedSession:
    user_id: str
    session_id: str
    greeting: str


def resolve_user_id(user_id: str | None) -> str:
    if user_id is None:
        return f"user_{uuid.uuid4().hex[:12]}"
    if not user_id.strip():
        raise InvalidSessionRequest("user_idを空文字列にはできません。")

    sanitized = streamlit_app.sanitize_user_id(user_id)
    if sanitized != user_id or not sanitized:
        raise InvalidSessionRequest("user_idの形式が不正です。")
    return sanitized


def _initial_greeting_system_prompt() -> str:
    return (
        "あなたはユーザー専属のパーソナルAI、Fairyです。\n"
        "新しい会話を始めるための、短く自然な挨拶を1つ作ってください。\n\n"
        "条件：\n"
        "- 誰にでも通用する内容にする\n"
        "- 過去の会話、性格、価値観、興味、プロフィールには触れない\n"
        "- 名前で呼びかける必要はない\n"
        "- 名前で呼びかける場合は、指定された表示名を一字一句変更せず使う\n"
        "- 指定された表示名以外の呼び名を作らない\n"
        "- 質問、雑談への誘い、相談の促し、手伝いの提案など、会話の始め方を毎回少し変える\n"
        "- 毎回「最近〜」で始めない\n"
        "- 毎回同じ定型表現を避ける\n"
        "- 重すぎる質問や、人生観・悩みをいきなり深掘りする質問にしない\n"
        "- 答えやすく、会話を始めやすい内容にする\n"
        "- 1〜2文\n"
        "- 80文字以内\n"
        "- 挨拶文だけを出力する\n"
        "- Markdown、JSON、引用符、説明文は出力しない"
    )


def _is_valid_greeting(text: str, display_name: str | None) -> bool:
    if not isinstance(text, str) or not text.strip() or len(text) > 80:
        return False
    if "```" in text:
        return False
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return False
    if "<" in text and ">" in text and (stripped.startswith("<") or stripped.endswith(">")):
        return False
    return all(display_name and name == display_name for name in re.findall(r"[^\s、。]*さん", text))


def generate_initial_greeting(display_name: str | None = DEFAULT_DISPLAY_NAME) -> str:
    """Generate a profile-independent greeting and fall back on every AI failure."""
    client = streamlit_app.get_openai_client()
    if client is None:
        return INITIAL_GREETING_FALLBACK

    user_message = (
        f"使用可能な表示名: {display_name}\n呼びかけは任意です。"
        if display_name
        else "表示名はありません。名前で呼びかけないでください。"
    )
    try:
        response = client.chat.completions.create(
            model=streamlit_app.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _initial_greeting_system_prompt()},
                {"role": "user", "content": user_message},
            ],
            temperature=0.9,
            max_completion_tokens=100,
        )
        text = response.choices[0].message.content.strip()
        return text if _is_valid_greeting(text, display_name) else INITIAL_GREETING_FALLBACK
    except Exception:
        return INITIAL_GREETING_FALLBACK


def create_initial_session_log(
    *, user_id: str, session_id: str, started_at: datetime.datetime, log_consent: bool
) -> Path:
    base = Path(streamlit_app.__file__).parent / "logs" / API_VERSION / "sessions"
    base.mkdir(parents=True, exist_ok=True)
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    short_id = session_id.rsplit("_", 1)[-1]
    path = base / f"session_{timestamp}_v{API_VERSION}_{short_id}.md"
    started_text = started_at.isoformat(timespec="seconds")
    lines = [
        "# AI分身マッチングMVP ログ",
        "",
        "## セッション情報",
        f"- app_version: v{API_VERSION}",
        f"- session_id: {session_id}",
        f"- user_id: {user_id}",
        f"- started_at: {started_text}",
        "- ended_at: 未完了",
        f"- log_consent: {str(log_consent).lower()}",
        f"- consented_at: {started_text}",
        "- session_status: started",
        "",
        "## チャット履歴",
        "",
        "まだチャット履歴はありません。",
        "",
        "## 分析結果",
        "",
        "まだ分析結果はありません。",
        "",
        "## マッチング結果",
        "",
        "まだマッチング結果はありません。",
    ]
    try:
        path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        raise SessionStartError("初期セッションログを作成できませんでした。") from exc

    metadata_path = path.with_suffix(".json")
    metadata = {
        "app_version": API_VERSION,
        "user_id": user_id,
        "session_id": session_id,
        "started_at": started_text,
        "log_consent": log_consent,
        "consented_at": started_text,
        "session_status": "started",
        "log_path": str(path),
    }
    try:
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise SessionStartError("セッション情報を記録できませんでした。") from exc
    return path


def start_session(user_id: str | None, log_consent: bool) -> StartedSession:
    if not log_consent:
        raise InvalidSessionRequest("ログ保存への同意が必要です。")

    resolved_user_id = resolve_user_id(user_id)
    session_id = streamlit_app.generate_session_id()
    started_at = datetime.datetime.now().astimezone()
    create_initial_session_log(
        user_id=resolved_user_id,
        session_id=session_id,
        started_at=started_at,
        log_consent=log_consent,
    )
    greeting = generate_initial_greeting()
    return StartedSession(
        user_id=resolved_user_id,
        session_id=session_id,
        greeting=greeting,
    )
