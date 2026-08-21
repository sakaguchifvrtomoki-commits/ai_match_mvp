from dataclasses import dataclass
import json
import re

import app as streamlit_app
from fairy_memory import build_fairy_memory_context
from api.storage import get_storage
from api.storage.base import NotFound


BASE_SYSTEM_PROMPT = (
    "あなたは相手の性格や価値観を丁寧に引き出すAIです。"
    " ユーザーが話した内容を受けて、次の質問や共感を返してください。"
    " ただし、深掘りしすぎず、優しく進めてください。"
)

MEMORY_RULES = (
    "\n\n【保存されたプロフィールの活用ルール】"
    "\n以下の情報はユーザーとの過去の会話から学んだ背景知識です。会話を自然に進めるための補助情報として使ってください。"
    "\n・今回のユーザーの発言を最優先してください。"
    "\n・発言と保存情報が矛盾する場合は、今回の発言を優先し、保存情報は活用しないでください。"
    "\n・保存情報を断定的な事実として扱わないでください。背景として参考にする程度にしてください。"
    "\n・『以前あなたは〜と言いました』のように不自然に記憶を明示しないでください。"
    "\n・保存情報と関連がある場合だけ、自然に活用してください。無関係な場合は持ち出さないでください。"
    "\n・質問の方向、共感、具体例をユーザーの関心に合わせて調整してください。"
    "\n・毎回同じ話題を持ち出さないでください。"
    "\n・保存情報にない情報を作り出さないでください。"
    "\n・プロフィールより、現在の会話の自然さを優先してください。"
)


class InvalidChatRequest(ValueError):
    """The chat request contains identifiers or history that cannot be used."""


class AIResponseFailed(RuntimeError):
    """The AI did not return a usable response."""


class AIResponseTruncated(AIResponseFailed):
    """The AI response stopped because of an output length limit."""


class AIContextTooLong(AIResponseFailed):
    """The AI request clearly exceeded the model context window."""


@dataclass(frozen=True)
class ChatReply:
    content: str


def validate_chat_identifiers(user_id: str, session_id: str) -> None:
    if streamlit_app.sanitize_user_id(user_id) != user_id:
        raise InvalidChatRequest("user_idの形式が不正です。")
    if not re.fullmatch(r"session_\d{8}_\d{6}_[0-9a-f]{6}", session_id):
        raise InvalidChatRequest("session_idの形式が不正です。")


def load_user_profile(user_id: str) -> dict:
    """Load and migrate a profile using v0.2.1 logic without Streamlit state/logging."""
    storage = get_storage()
    try:
        raw_profile = storage.load_profile(user_id)
    except NotFound:
        return streamlit_app._empty_profile(user_id)
    if not isinstance(raw_profile, dict):
        raise streamlit_app.ProfileLoadError("プロフィールが辞書型ではありません")

    needs_migration = (
        raw_profile.get("profile_version", "0.1.0")
        != streamlit_app.CURRENT_PROFILE_VERSION
    )
    if needs_migration:
        # A backup is required before a migration can modify the source profile.
        storage.backup_profile_before_migration(user_id)

    profile = streamlit_app.migrate_profile(raw_profile)
    profile["summary"] = streamlit_app.normalize_summary(profile.get("summary", ""))
    profile["matching_hypothesis"] = streamlit_app.normalize_matching_hypothesis(
        profile.get("matching_hypothesis", {})
    )
    streamlit_app.validate_profile(profile)
    if needs_migration:
        storage.save_profile(user_id, profile)
    return profile


def build_system_prompt(user_id: str) -> str:
    """Build the v0.2.1 conversation prompt without Streamlit session state."""
    try:
        profile = load_user_profile(user_id)
        memory_context, _ = build_fairy_memory_context(profile)
    except Exception:
        # v0.2.1 also continues with the base prompt when profile loading fails.
        # No profile is created or saved on this path.
        return BASE_SYSTEM_PROMPT

    if not memory_context:
        return BASE_SYSTEM_PROMPT
    return BASE_SYSTEM_PROMPT + MEMORY_RULES + f"\n\n【背景情報】\n{memory_context}"


def _is_context_too_long_error(exc: Exception) -> bool:
    body = getattr(exc, "body", None)
    error_code = ""
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            error_code = str(error.get("code", ""))
    text = f"{error_code} {exc}".lower()
    return any(
        marker in text
        for marker in (
            "context_length_exceeded",
            "maximum context length",
            "maximum context window",
            "context window is too long",
            "too many tokens",
        )
    )


def generate_chat_reply(user_id: str, session_id: str, messages: list[dict]) -> ChatReply:
    validate_chat_identifiers(user_id, session_id)
    client = streamlit_app.get_openai_client()
    if client is None:
        raise AIResponseFailed("Fairyから応答を取得できませんでした。")

    request_messages = [{"role": "system", "content": build_system_prompt(user_id)}]
    request_messages.extend(
        {"role": message["role"], "content": message["content"]}
        for message in messages
    )

    try:
        response = client.chat.completions.create(
            model=streamlit_app.OPENAI_MODEL,
            messages=request_messages,
            max_completion_tokens=500,
            temperature=0.9,
        )
    except Exception as exc:
        if _is_context_too_long_error(exc):
            raise AIContextTooLong("会話履歴が長すぎます。短くして再試行してください。") from exc
        if exc.__class__.__name__ == "LengthFinishReasonError":
            raise AIResponseTruncated("Fairyの応答が途中で切れました。再試行してください。") from exc
        raise AIResponseFailed("Fairyから応答を取得できませんでした。") from exc

    try:
        choice = response.choices[0]
        finish_reason = choice.finish_reason
        content = choice.message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise AIResponseFailed("Fairyから有効な応答を取得できませんでした。") from exc

    if finish_reason == "length":
        raise AIResponseTruncated("Fairyの応答が途中で切れました。再試行してください。")
    if not isinstance(content, str) or not content.strip():
        raise AIResponseFailed("Fairyから有効な応答を取得できませんでした。")
    return ChatReply(content=content.strip())
