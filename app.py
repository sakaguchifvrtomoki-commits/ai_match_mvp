import datetime
import json
import math
import os
import traceback
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

APP_VERSION = "0.0.3"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def get_openai_client():
    if not OPENAI_API_KEY:
        return None
    return OpenAI(api_key=OPENAI_API_KEY)


def ensure_log_dirs():
    base = Path(__file__).parent / "logs" / APP_VERSION
    for sub in ("sessions", "debug", "errors"):
        (base / sub).mkdir(parents=True, exist_ok=True)


def get_log_paths():
    base = Path(__file__).parent / "logs" / APP_VERSION
    return {
        "sessions_dir": base / "sessions",
        "debug_file": base / "debug" / "debug.jsonl",
        "error_file": base / "errors" / "error.jsonl",
    }


def generate_session_id() -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"session_{ts}_{uuid.uuid4().hex[:6]}"


def get_or_create_session_id() -> str:
    if not st.session_state.get("session_id"):
        st.session_state.session_id = generate_session_id()
    return st.session_state.session_id


def write_debug_log(event: str, data=None):
    try:
        paths = get_log_paths()
        entry = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "session_id": get_or_create_session_id(),
            "event": event,
        }
        if data is not None:
            entry["data"] = data
        with open(paths["debug_file"], "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        st.warning("デバッグログの書き込みに失敗しました（アプリの動作には影響しません）。")


def write_error_log(event: str, error_message: str, data=None):
    try:
        paths = get_log_paths()
        entry = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "session_id": get_or_create_session_id(),
            "event": event,
            "error": error_message,
        }
        if data is not None:
            entry["data"] = data
        with open(paths["error_file"], "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        st.warning("エラーログの書き込みに失敗しました（アプリの動作には影響しません）。")


def save_session_markdown_log(session_status: str = "completed", end_reason: str = None):
    try:
        session_id = get_or_create_session_id()
        consent_value = str(st.session_state.get("log_consent", "")).lower()
        consented_at = st.session_state.get("consented_at", "")
        started_at = st.session_state.get("session_started_at", consented_at)
        ended_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_info = [
            "# AI分身マッチングMVP ログ",
            "",
            "## セッション情報",
            f"- app_version: v{APP_VERSION}",
            f"- session_id: {session_id}",
            f"- started_at: {started_at}",
            f"- ended_at: {ended_at}",
            f"- log_consent: {consent_value}",
            f"- consented_at: {consented_at}",
            f"- session_status: {session_status}",
        ]
        if end_reason:
            session_info.append(f"- end_reason: {end_reason}")
        lines = session_info + ["", "## チャット履歴"]
        for msg in st.session_state.get("messages", []):
            role = msg.get("role", "")
            content = msg.get("content", "")
            lines.append(f"[{role}]: {content}")

        analysis = st.session_state.get("analysis_result")
        if analysis:
            lines += [
                "",
                "## 分析結果",
                f"性格傾向: {analysis.get('personality', '')}",
                f"価値観: {analysis.get('values', '')}",
                f"隠れた欲求: {analysis.get('hidden_needs', '')}",
                f"会話スタイル: {analysis.get('communication_style', '')}",
                f"理想の相手像: {analysis.get('ideal_partner_type', '')}",
                f"一言要約: {analysis.get('summary', '')}",
            ]

        match = st.session_state.get("match_result")
        if match:
            candidate = match.get("matched_candidate", {})
            lines += [
                "",
                "## マッチング結果",
                f"マッチ相手: {candidate.get('name', '')} ({candidate.get('age', '')}歳)",
                f"説明: {candidate.get('description', '')}",
                f"相性タイプ: {match.get('match_label', '')}",
                f"相性ポイント: {match.get('match_reason', '')}",
                f"注意点: {match.get('possible_concern', '')}",
                f"最初のメッセージ: {match.get('recommended_first_message', '')}",
            ]

        top_matches = st.session_state.get("top_match_candidates")
        analysis_for_log = st.session_state.get("analysis_result") or {}
        if top_matches:
            other_candidates = [item for item in top_matches[1:3] if item.get("candidate")]
            if other_candidates:
                lines += ["", "## 他にも相性が近かった候補者"]
                for idx, item in enumerate(other_candidates, start=2):
                    c = item["candidate"]
                    reason = generate_short_candidate_reason(analysis_for_log, c)
                    lines.append(f"{idx}位: {c.get('name', '')} ({c.get('age', '')}歳) — {reason}")

        support = st.session_state.get("after_match_support")
        if support:
            lines += [
                "",
                "## マッチ後支援",
                f"今日送る一言: {support.get('first_message_today', '')}",
                f"3日以内に聞く質問: {support.get('question_in_3days', '')}",
                f"避けたほうがいい一言: {support.get('avoid_phrase', '')}",
                f"返信が遅いときの対応: {support.get('slow_reply_action', '')}",
            ]

        log_path_str = st.session_state.get("session_log_path")
        if log_path_str:
            log_path = Path(log_path_str)
        else:
            paths = get_log_paths()
            log_path = paths["sessions_dir"] / f"{session_id}.md"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        st.warning("セッションログの保存に失敗しました（アプリの動作には影響しません）。")


def create_initial_session_log():
    try:
        write_debug_log("session_markdown_initial_save_started", {
            "level": "INFO",
            "message": "初期session Markdownログの保存を開始しました",
        })
        session_id = get_or_create_session_id()
        parts = session_id.split("_")
        if len(parts) == 4 and parts[0] == "session":
            ts = f"{parts[1]}_{parts[2]}"
            short_id = parts[3]
        else:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            short_id = "unknown"
        filename = f"session_{ts}_v{APP_VERSION}_{short_id}.md"

        paths = get_log_paths()
        log_path = paths["sessions_dir"] / filename

        started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.session_started_at = started_at
        consented_at = st.session_state.get("consented_at", started_at)
        consent_value = str(st.session_state.get("log_consent", "")).lower()
        lines = [
            "# AI分身マッチングMVP ログ",
            "",
            "## セッション情報",
            f"- app_version: v{APP_VERSION}",
            f"- session_id: {session_id}",
            f"- started_at: {started_at}",
            "- ended_at: 未完了",
            f"- log_consent: {consent_value}",
            f"- consented_at: {consented_at}",
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
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        st.session_state.session_log_path = str(log_path)
        write_debug_log("session_markdown_initial_save_finished", {
            "level": "INFO",
            "message": "初期session Markdownログの保存が完了しました",
            "path": str(log_path),
        })
    except Exception as e:
        write_debug_log("session_markdown_initial_save_failed", {
            "level": "ERROR",
            "message": "初期session Markdownログの保存に失敗しました",
        })
        write_error_log("session_markdown_initial_save_failed", str(e))
        st.warning("初期セッションログの作成に失敗しました（アプリの動作には影響しません）。")


def has_log_consent() -> bool:
    return st.session_state.get("consent_status") == "accepted"


def record_consent_event(accepted: bool):
    if accepted:
        write_debug_log("log_consent_accepted", {
            "level": "INFO",
            "message": "ユーザーがログ保存に同意しました",
        })
    else:
        write_debug_log("log_consent_declined", {
            "level": "INFO",
            "message": "ユーザーがログ保存に同意しませんでした",
        })


def show_consent_screen():
    st.subheader("ログ保存への同意確認")
    st.write("このアプリでは、品質改善・動作確認のため、以下の情報を保存します。")
    st.markdown(
        "- チャット履歴\n"
        "- 分析結果\n"
        "- マッチング結果\n"
        "- デバッグ情報\n"
        "- エラー情報"
    )
    st.write("保存されたログは開発・検証目的でのみ使用します。")
    st.write("GitHubなどの公開場所には保存しません。")
    st.write("同意する場合のみ、チャットを開始できます。")

    choice = st.radio(
        "ログ保存への同意",
        ["ログ保存に同意します", "ログ保存に同意しません"],
        index=None,
        label_visibility="collapsed",
    )

    if st.button("チャットを開始する", key="start_chat"):
        if choice is None:
            st.warning("同意するかどうかを選択してください。")
        elif choice == "ログ保存に同意します":
            ts_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.consent_status = "accepted"
            st.session_state.log_consent = True
            st.session_state.consented_at = ts_str
            st.session_state.session_id = generate_session_id()
            record_consent_event(accepted=True)
            create_initial_session_log()
            st.rerun()
        else:
            st.session_state.consent_status = "declined"
            st.session_state.log_consent = False
            record_consent_event(accepted=False)
            st.rerun()


def show_consent_declined_screen():
    st.warning("ログ保存に同意されなかったため、チャットを開始できません。")
    st.write(
        "このMVPでは、品質改善・動作確認のためにログ保存が必要です。\n"
        "チャットを利用する場合は、前の画面に戻って「ログ保存に同意します」を選択してください。"
    )
    if st.button("戻る", key="back_to_consent"):
        st.session_state.consent_status = None
        st.session_state.log_consent = None
        st.rerun()


def _reset_chat_state():
    st.session_state.is_processing = False
    st.session_state.messages = [{"role": "assistant", "content": initial_question()}]
    st.session_state.analysis_result = None
    st.session_state.match_result = None
    st.session_state.after_match_support = None
    st.session_state.top_match_candidates = None
    st.session_state.last_analysis_response = None
    st.session_state.last_analysis_error = None
    st.session_state.last_match_response = None
    st.session_state.last_match_error = None
    st.session_state.match_details_raw_response = None
    st.session_state.match_details_error = None
    st.session_state.selected_candidate_debug = None
    st.session_state.last_after_match_support_response = None
    st.session_state.last_after_match_support_error = None
    st.session_state.last_reply_finish_reason = None


def handle_restart():
    write_debug_log("session_restart_requested", {
        "level": "INFO",
        "message": "ユーザーが最初からやり直すボタンを押しました",
    })
    save_session_markdown_log(session_status="ended_by_restart", end_reason="user_clicked_restart")

    st.session_state.session_id = generate_session_id()
    st.session_state.session_log_path = None
    st.session_state.consented_at = st.session_state.get("consented_at", "")

    _reset_chat_state()
    create_initial_session_log()
    st.rerun()


def handle_finish():
    write_debug_log("session_finished_by_user", {
        "level": "INFO",
        "message": "ユーザーが終わるボタンを押してセッションを終了しました",
    })
    save_session_markdown_log(session_status="completed", end_reason="user_clicked_finish")

    for key in [
        "consent_status", "log_consent", "consented_at",
        "session_id", "session_started_at", "session_log_path",
        "messages", "analysis_result", "match_result", "after_match_support",
        "top_match_candidates", "last_analysis_response", "last_analysis_error",
        "last_match_response", "last_match_error", "match_details_raw_response",
        "match_details_error", "selected_candidate_debug",
        "last_after_match_support_response", "last_after_match_support_error",
        "last_reply_finish_reason",
    ]:
        st.session_state.pop(key, None)
    st.rerun()


def handle_restart_after_analysis():
    write_debug_log("session_restart_requested_after_analysis", {
        "level": "INFO",
        "message": "分析後にユーザーが最初からやり直すボタンを押しました",
    })
    save_session_markdown_log(
        session_status="ended_by_restart",
        end_reason="user_clicked_restart_after_analysis",
    )
    st.session_state.session_id = generate_session_id()
    st.session_state.session_log_path = None
    _reset_chat_state()
    create_initial_session_log()
    st.rerun()


def load_candidates():
    path = Path(__file__).parent / "candidates.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def initial_question() -> str:
    return "あなたが最近、楽しかったことや少し気になっていることを教えてください。"


def ensure_session_state():
    ensure_log_dirs()
    if "consent_status" not in st.session_state:
        st.session_state.consent_status = None
    if "log_consent" not in st.session_state:
        st.session_state.log_consent = None
    if "consented_at" not in st.session_state:
        st.session_state.consented_at = None
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "session_started_at" not in st.session_state:
        st.session_state.session_started_at = None
    if "session_log_path" not in st.session_state:
        st.session_state.session_log_path = None
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": initial_question()}]
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "match_result" not in st.session_state:
        st.session_state.match_result = None
    if "after_match_support" not in st.session_state:
        st.session_state.after_match_support = None
    if "top_match_candidates" not in st.session_state:
        st.session_state.top_match_candidates = None
    if "last_analysis_response" not in st.session_state:
        st.session_state.last_analysis_response = None
    if "last_analysis_error" not in st.session_state:
        st.session_state.last_analysis_error = None
    if "last_match_response" not in st.session_state:
        st.session_state.last_match_response = None
    if "last_match_error" not in st.session_state:
        st.session_state.last_match_error = None
    if "match_details_raw_response" not in st.session_state:
        st.session_state.match_details_raw_response = None
    if "match_details_error" not in st.session_state:
        st.session_state.match_details_error = None
    if "selected_candidate_debug" not in st.session_state:
        st.session_state.selected_candidate_debug = None
    if "last_after_match_support_response" not in st.session_state:
        st.session_state.last_after_match_support_response = None
    if "last_after_match_support_error" not in st.session_state:
        st.session_state.last_after_match_support_error = None
    if "last_reply_finish_reason" not in st.session_state:
        st.session_state.last_reply_finish_reason = None


def render_chat():
    for message in st.session_state.messages:
        if message["role"] == "assistant":
            with st.chat_message("assistant"):
                st.write(message["content"])
        else:
            with st.chat_message("user"):
                st.write(message["content"])


def build_system_prompt() -> str:
    return (
        "あなたは相手の性格や価値観を丁寧に引き出すAIです。"
        " ユーザーが話した内容を受けて、次の質問や共感を返してください。"
        " ただし、深掘りしすぎず、優しく進めてください。"
    )


def generate_ai_reply(chat_history):
    client = get_openai_client()
    if client is None:
        return "OPENAI_API_KEY が設定されていません。"

    messages = [
        {"role": "system", "content": build_system_prompt()},
    ]
    messages.extend(chat_history)

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_completion_tokens=500,
            temperature=0.9,
        )
        content = response.choices[0].message.content.strip()
        finish_reason = response.choices[0].finish_reason
        st.session_state.last_reply_finish_reason = finish_reason

        if finish_reason == "length":
            return (
                f"{content}\n\n※応答が途中で切れている可能性があります。"
                f" (finish_reason={finish_reason})"
            )

        return content
    except Exception as e:
        return f"AI応答の取得中にエラーが発生しました: {e}"


def extract_json(text: str):
    try:
        start = text.index("{")
        end = text.rindex("}")
        return json.loads(text[start:end + 1])
    except Exception:
        try:
            return json.loads(text)
        except Exception:
            return None


def validate_analysis_result(analysis):
    required_keys = [
        "personality",
        "values",
        "hidden_needs",
        "communication_style",
        "ideal_partner_type",
        "summary",
    ]

    if not isinstance(analysis, dict):
        return False, "analysis が dict ではありません。"

    for key in required_keys:
        if key not in analysis:
            return False, f"{key} がありません。"
        if not isinstance(analysis[key], str):
            return False, f"{key} が文字列ではありません。"
        if not analysis[key].strip():
            return False, f"{key} が空です。"

    return True, None


def analyze_user(chat_history):
    client = get_openai_client()
    if client is None:
        return None

    conversation = "\n".join(
        [f"[{msg['role']}]: {msg['content']}" for msg in chat_history]
    )
    prompt = (
        "あなたはユーザーの性格、価値観、本音を分析するアシスタントです。"
        " 以下の会話履歴から、JSON形式で分析結果を出力してください。\n\n"
        "【出力形式】\n"
        "以下の6つのキーを持つJSONオブジェクトのみを出力してください。\n"
        "{\n"
        '  "personality": "100〜180字程度で、性格傾向を要約",\n'
        '  "values": "100〜180字程度で、大切にしている価値観を要約",\n'
        '  "hidden_needs": "100〜180字程度で、隠れた欲求を要約",\n'
        '  "communication_style": "100〜180字程度で、会話スタイルを要約",\n'
        '  "ideal_partner_type": "100〜180字程度で、相性が良い相手像を要約",\n'
        '  "summary": "80〜140字程度で、一言要約"\n'
        "}\n\n"
        "【制約】\n"
        "- JSONのみを出力すること。Markdownコードブロック（```json）は使わないこと\n"
        "- JSONの外に説明文を出さないこと\n"
        "- 各値は必ず文字列にすること。配列にしないこと\n"
        "- 各項目は100〜180字程度に収めること（summary は80〜140字）\n"
        "- 断定調を避けて「〜かもしれません」「〜の可能性があります」を使うこと\n"
        "- 会話履歴から具体的な引用を1つ含めること\n\n"
        f"会話履歴:\n{conversation}\n"
    )
    write_debug_log("analysis_started", {"message_count": len(chat_history)})
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "あなたは日本語でユーザーの性格・価値観を分析し、必ず有効なJSONのみを返すアシスタントです。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_completion_tokens=1200,
            response_format={"type": "json_object"},
        )
        st.session_state.last_analysis_response = response.choices[0].message.content.strip()
        analysis = extract_json(st.session_state.last_analysis_response)
        if analysis is None:
            st.session_state.last_analysis_error = "JSON解析に失敗しました。"
            write_error_log("analysis_json_parse_failed", "JSON解析に失敗しました。")
            return None

        is_valid, error_message = validate_analysis_result(analysis)
        if not is_valid:
            st.session_state.last_analysis_error = f"分析結果の形式が不正です: {error_message}"
            write_error_log("analysis_validation_failed", error_message)
            return None

        st.session_state.last_analysis_error = None
        write_debug_log("analysis_finished")
        return analysis
    except Exception as e:
        st.session_state.last_analysis_error = str(e)
        st.session_state.last_analysis_response = None
        write_error_log("analysis_exception", str(e))
        return None


def build_profile_text(candidate):
    parts = [
        f"名前: {candidate.get('name', '未設定')}",
        f"年齢: {candidate.get('age', '未設定')}",
        f"性格: {candidate.get('personality', '')}",
        f"価値観: {candidate.get('values', '')}",
        f"趣味: {candidate.get('hobbies', '')}",
        f"会話スタイル: {candidate.get('communication_style', '')}",
        f"関係性スタイル: {candidate.get('relationship_style', '')}",
        f"説明: {candidate.get('description', '')}",
    ]
    return "。".join(parts)


def build_analysis_text(analysis):
    if not analysis:
        return ""
    return "。".join(
        [
            f"性格傾向: {analysis.get('personality','')}",
            f"価値観: {analysis.get('values','')}",
            f"隠れた欲求: {analysis.get('hidden_needs','')}",
            f"会話スタイル: {analysis.get('communication_style','')}",
            f"理想の相手像: {analysis.get('ideal_partner_type','')}",
            f"要約: {analysis.get('summary','')}",
        ]
    )


def get_embedding(client, text):
    if not text:
        return []
    response = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def choose_top_candidates(analysis, candidates, top_n=3):
    client = get_openai_client()
    if client is None or analysis is None:
        return []

    analysis_text = build_analysis_text(analysis)
    analysis_emb = get_embedding(client, analysis_text)
    candidates_with_scores = []

    for candidate in candidates:
        candidate_text = build_profile_text(candidate)
        candidate_emb = get_embedding(client, candidate_text)
        score = cosine_similarity(analysis_emb, candidate_emb)
        candidates_with_scores.append({
            "candidate": candidate,
            "similarity": score
        })

    # similarity の高い順にソート
    candidates_with_scores.sort(key=lambda x: x["similarity"], reverse=True)
    return candidates_with_scores[:top_n]


def choose_best_candidate(analysis, candidates):
    top_matches = choose_top_candidates(analysis, candidates, top_n=1)
    return top_matches[0] if top_matches else None


def build_reason_prompt(analysis, candidate):
    """（旧実装は廃止。新しい build_match_details_prompt() を使用）"""
    return ""



_MATCH_TYPE_KEYWORDS = {
    "安心感重視タイプ": ["安心", "落ち着", "信頼", "穏やか", "安定", "安全"],
    "深い対話タイプ":   ["深い話", "深い対話", "内面", "本音", "感受性", "繊細", "共感"],
    "境界線尊重タイプ": ["距離感", "ペース", "境界", "尊重", "自立"],
    "行動伴走タイプ":   ["行動", "挑戦", "一緒に", "伴走", "冒険", "体験", "成長"],
    "関係継続サポートタイプ": ["続ける", "継続", "返信", "連絡", "長く", "関係を育"],
    "会話の広がりタイプ": ["雑談", "趣味", "広がり", "楽し", "話題"],
    "価値観共鳴タイプ": ["考え方", "人生観", "価値観", "共鳴", "共有"],
}

_SHORT_REASON_TEMPLATES = {
    "安心感重視タイプ":       "安心感や落ち着いたやり取りを大切にしながら、関係を作りやすい候補です。",
    "深い対話タイプ":         "深い対話や価値観の共有を通じて、ゆっくり距離を縮めやすい候補です。",
    "境界線尊重タイプ":       "お互いのペースや距離感を尊重しながら、無理なく関係を進めやすい候補です。",
    "行動伴走タイプ":         "一緒に行動したり挑戦を共有したりする中で、自然に距離が縮まりやすい候補です。",
    "関係継続サポートタイプ": "連絡の続け方や関係の育て方を意識しながら、長く関係を作りやすい候補です。",
    "会話の広がりタイプ":     "日常の話題や趣味の共有から、会話が自然に広がりやすい候補です。",
    "価値観共鳴タイプ":       "考え方や大切にしている価値観が響き合いやすい候補です。",
}


def assign_match_type(analysis: dict, candidate: dict) -> str:
    """ユーザー分析と候補者プロフィールのキーワードから相性の種類を返す。APIコール不要。"""
    combined = " ".join([
        analysis.get("personality", ""),
        analysis.get("values", ""),
        analysis.get("hidden_needs", ""),
        analysis.get("ideal_partner_type", ""),
        candidate.get("personality", ""),
        candidate.get("values", ""),
        candidate.get("communication_style", ""),
        candidate.get("relationship_style", ""),
    ])
    scores = {label: sum(1 for w in words if w in combined)
              for label, words in _MATCH_TYPE_KEYWORDS.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "深い対話タイプ"


def generate_short_candidate_reason(analysis: dict, candidate: dict) -> str:
    """第2・第3候補用の短い説明文を返す。OpenAI APIは使わない。"""
    match_type = assign_match_type(analysis, candidate)
    return _SHORT_REASON_TEMPLATES.get(match_type, "あなたの傾向に近い部分がある候補です。")


def build_match_result(analysis, candidate, similarity):
    """マッチング詳細情報を生成し、マッチング結果を構築する。"""
    # デバッグ情報保存
    st.session_state.selected_candidate_debug = candidate
    
    details = generate_match_details(analysis, candidate)
    
    if details is None:
        st.error("マッチング詳細情報の生成に失敗しました。デバッグ情報を確認してください。")
        return None

    return {
        "matched_candidate": candidate,
        "match_score": min(max(int(similarity * 100), 0), 100),
        "match_label": assign_match_type(analysis, candidate),
        "match_reason": details.get("reason", ""),
        "possible_concern": details.get("caution", ""),
        "recommended_first_message": details.get("first_message", ""),
    }


def validate_match_details(details):
    if not details:
        return False, "details が空です。"

    required_keys = ["reason", "caution", "first_message"]
    for key in required_keys:
        if key not in details:
            return False, f"{key} がありません。"

    forbidden_phrases = [
        "この候補者はあなたの価値観や会話スタイルとよく合っている可能性があります",
        "違いがある場合は、お互いのペースを確認することが大切かもしれません",
        "最近のことや興味を持っていることについて気軽に話しかけてみましょう"
    ]

    text = str(details)
    for phrase in forbidden_phrases:
        if phrase in text:
            return False, f"禁止文が検出されました: {phrase}"

    if len(details.get("reason", "")) < 250:
        return False, "reason が短すぎます。"

    if len(details.get("caution", "")) < 150:
        return False, "caution が短すぎます。"

    if len(details.get("first_message", "")) < 20:
        return False, "first_message が短すぎます。"

    return True, None


def generate_match_details(analysis, candidate, conversation_summary=""):
    """
    マッチング詳細情報（reason, caution, first_message）を生成する。
    禁止文が含まれた場合は再生成。
    """
    client = get_openai_client()
    if client is None:
        return None
    
    prompt = build_match_details_prompt(analysis, candidate, conversation_summary)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "あなたは日本語で具体的で差別化されたマッチング情報をJSON形式で出力するアシスタントです。汎用文は避け、常に具体的な語を使用してください。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_completion_tokens=2000,
            )
            
            raw_response = response.choices[0].message.content.strip()
            st.session_state.match_details_raw_response = raw_response
            
            details = extract_json(raw_response)
            if details is None:
                st.session_state.match_details_error = f"JSON解析に失敗しました（試行 {attempt+1}/{max_retries}）"
                continue
            
            is_valid, error_message = validate_match_details(details)
            
            if not is_valid:
                st.session_state.match_details_error = f"{error_message}（試行 {attempt+1}/{max_retries}）"
                continue
            
            st.session_state.match_details_error = None
            return details
            
        except Exception as e:
            st.session_state.match_details_error = f"エラー: {str(e)}（試行 {attempt+1}/{max_retries}）"
    
    st.session_state.match_details_error = f"マッチング詳細情報の生成に失敗しました（{max_retries}回の試行後）。"
    return None


def build_match_details_prompt(analysis, candidate, conversation_summary=""):
    """マッチング詳細情報を生成するプロンプトを構築する"""
    return (
        "あなたはAIマッチングアシスタントです。"
        " 以下の情報をもとに、具体的で差別化されたマッチング詳細情報をJSON形式で出力してください。\n\n"
        "【重要な制約】\n"
        "1. reason フィールドには、ユーザー分析と候補者プロフィールの具体語をそれぞれ3つ以上含め、なぜこのマッチングが良いのかを会話履歴やプロフィールから具体的な例を挙げて説明すること。\n"
        "2. reason フィールドに『この候補者はあなたの価値観や会話スタイルとよく合っている可能性があります』のような汎用文を絶対に含めないこと。\n"
        "3. caution フィールドには、ユーザーと候補者のズレやすい具体的なポイントを挙げ、建設的なアドバイスを含めて説明し、『違いがある場合は、お互いのペースを確認することが大切かもしれません』のような抽象文を絶対に含めないこと。\n"
        "4. first_message フィールドは、候補者の趣味・価値観に具体的に触れ、ユーザーの特徴も入れ、自然でパーソナライズされたメッセージにすること。『最近のことや興味を持っていることについて気軽に話しかけてみましょう』のような汎用文にしないこと。\n"
        "5. reason には最低400字、caution には最低250字の内容を含めること。\n\n"
        "【ユーザー分析】\n"
        f"性格傾向: {analysis.get('personality','')}\n"
        f"価値観: {analysis.get('values','')}\n"
        f"隠れた欲求: {analysis.get('hidden_needs','')}\n"
        f"会話スタイル: {analysis.get('communication_style','')}\n"
        f"理想の相手像: {analysis.get('ideal_partner_type','')}\n"
        f"要約: {analysis.get('summary','')}\n\n"
        "【候補者プロフィール】\n"
        f"名前: {candidate.get('name', '未設定')}\n"
        f"年齢: {candidate.get('age', '未設定')}\n"
        f"性格: {candidate.get('personality', '')}\n"
        f"価値観: {candidate.get('values', '')}\n"
        f"趣味: {candidate.get('hobbies', '')}\n"
        f"会話スタイル: {candidate.get('communication_style', '')}\n"
        f"関係性スタイル: {candidate.get('relationship_style', '')}\n"
        f"説明: {candidate.get('description', '')}\n\n"
        "【出力形式】\n"
        "JSON のみで、必ず以下のキーを含めてください。\n"
        "{\n"
        '  "reason": "ユーザーの具体的な特性と候補者の具体的な特性を接続させ、なぜこの相手が合うのかを400字以上で説明。",\n'
        '  "caution": "ユーザーと候補者のズレやすい具体的なポイント、温度差が出やすい場面を250字以上で説明。",\n'
        '  "first_message": "候補者のプロフィールに具体的に触れ、ユーザーの特徴も入れた自然なメッセージ。"\n'
        "}\n\n"
        "【禁止事項】\n"
        "- 『価値観や会話スタイルとよく合っている可能性があります』という汎用文\n"
        "- 『違いがある場合は、お互いのペースを確認することが大切かもしれません』という抽象文\n"
        "- 『気軽に話しかけてみましょう』という汎用メッセージ\n\n"
        "ユーザー個別、候補者個別の具体的な内容を出力してください。"
    )


def generate_match(analysis, candidates):
    """
    2. マッチングAI：分析結果を受け取り、相性の良い候補者を選んでマッチング理由を生成する。
    
    Args:
        analysis: ユーザー分析結果（analyze_user()の戻り値）
        candidates: 候補者リスト
    
    Returns:
        マッチング結果（matched_candidate, match_score, match_reason等を含む）
    """
    if analysis is None:
        st.session_state.last_match_error = "分析結果がありません。"
        return None

    if not candidates:
        st.session_state.last_match_error = "候補者がありません。"
        return None

    write_debug_log("matching_started", {"candidate_count": len(candidates)})

    # ステップ1: 埋め込みベースで候補者を絞る
    top_matches = choose_top_candidates(analysis, candidates, top_n=3)
    if not top_matches:
        st.session_state.last_match_error = "候補者を選出できませんでした。"
        write_error_log("matching_no_candidates", "候補者を選出できませんでした。")
        return None

    st.session_state.top_match_candidates = top_matches
    best_match = top_matches[0]

    # ステップ2: AIに詳細なマッチング理由を生成させる
    match_result = build_match_result(analysis, best_match["candidate"], best_match["similarity"])

    if match_result:
        write_debug_log("matching_finished", {"matched_id": best_match["candidate"].get("id"), "score": best_match["similarity"]})

    return match_result


def build_after_match_support_prompt(analysis, match_result):
    """マッチ後支援AIのプロンプトを構築する（4項目固定）"""
    candidate = match_result["matched_candidate"]
    return (
        "あなたはAI分身マッチングのマッチ後支援アシスタントです。\n\n"
        "以下のユーザー分析とマッチ相手の情報をもとに、実際にすぐ使える4項目をJSON形式で出力してください。\n\n"
        "【ユーザー分析】\n"
        f"性格傾向: {analysis.get('personality','')}\n"
        f"価値観: {analysis.get('values','')}\n"
        f"隠れた欲求: {analysis.get('hidden_needs','')}\n"
        f"要約: {analysis.get('summary','')}\n\n"
        "【マッチ相手】\n"
        f"名前: {candidate.get('name','')}\n"
        f"性格: {candidate.get('personality','')}\n"
        f"会話スタイル: {candidate.get('communication_style','')}\n"
        f"関係性スタイル: {candidate.get('relationship_style','')}\n\n"
        "【出力形式】JSONのみ。以下の4キーのみ出力してください。\n"
        "{\n"
        '  "first_message_today": "今日実際に送れる一言メッセージ（1〜2文）",\n'
        '  "question_in_3days": "3日以内に聞くとよい質問（1文）",\n'
        '  "avoid_phrase": "避けたほうがいい言葉と、その理由（2〜3文）",\n'
        '  "slow_reply_action": "返信が遅いときにとるべき行動（1〜2文）"\n'
        "}\n\n"
        "【制約】\n"
        "- 抽象的な助言を書かない。実際に送れる文・取れる行動を書く\n"
        "- 1項目あたり1〜3文以内に収める\n"
        "- 長い箇条書きは禁止\n"
        "- JSONのみ出力。Markdownコードブロック禁止"
    )


def generate_after_match_support(analysis, match_result):
    """
    3. マッチ後支援AI：マッチ後に関係が続きやすくなるための支援方針を生成する。
    
    Args:
        analysis: ユーザー分析結果
        match_result: マッチング結果
    
    Returns:
        マッチ後支援（relationship_key_points, first_week_approach等を含む）
    """
    client = get_openai_client()
    if client is None:
        st.session_state.last_after_match_support_error = "OpenAI APIが利用できません。"
        return None
    
    if analysis is None or match_result is None:
        st.session_state.last_after_match_support_error = "分析結果またはマッチ結果がありません。"
        return None
    
    prompt = build_after_match_support_prompt(analysis, match_result)
    
    write_debug_log("support_started")
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "あなたは日本語で丁寧に回答し、JSON形式で出力するアシスタントです。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_completion_tokens=2500,
        )
        st.session_state.last_after_match_support_response = response.choices[0].message.content.strip()
        support = extract_json(st.session_state.last_after_match_support_response)

        if support is None:
            st.session_state.last_after_match_support_error = "JSON解析に失敗しました。"
            write_error_log("support_json_parse_failed", "JSON解析に失敗しました。")
            return None

        st.session_state.last_after_match_support_error = None
        write_debug_log("support_finished")
        return support

    except Exception as e:
        st.session_state.last_after_match_support_error = str(e)
        st.session_state.last_after_match_support_response = None
        write_error_log("support_exception", str(e))
        return None


def render_support_field(label, value):
    st.write(f"**{label}:**")
    if isinstance(value, list):
        for item in value:
            st.markdown(f"- {item}")
    elif isinstance(value, str):
        st.write(value)
    else:
        st.write(value)


def run_matching():
    """
    マッチング処理全体を3段階で実行：
    1. ユーザー分析
    2. マッチング（候補者選出）
    3. マッチ後支援方針の生成
    """
    st.session_state.top_match_candidates = None
    candidates = load_candidates()
    analysis = st.session_state.analysis_result
    
    if analysis is None:
        return None

    # ステップ2: マッチング
    with st.spinner("相性の高い候補者を探しています..."):
        match_result = generate_match(analysis, candidates)
        if match_result is None:
            st.error("マッチング処理に失敗しました。")
            return None
        st.session_state.match_result = match_result
    
    # ステップ3: マッチ後支援の生成
    with st.spinner("マッチ後の支援方針を作成中です..."):
        after_match_support = generate_after_match_support(analysis, match_result)
        if after_match_support is not None:
            st.session_state.after_match_support = after_match_support
        else:
            st.warning("マッチ後支援の生成に失敗しました。今後の機能向上にお役立てします。")

    save_session_markdown_log()
    write_debug_log("session_log_saved")

    return match_result


def main():
    st.set_page_config(page_title=f"AI分身マッチングMVP v{APP_VERSION}", layout="centered")
    st.title(f"AI分身マッチングMVP v{APP_VERSION}")
    st.write(
        "AIとの対話を通じて、あなたの性格や価値観を分析し、相性のよさそうな候補者を1人紹介します。"
    )

    if not OPENAI_API_KEY:
        st.error("OPENAI_API_KEY が設定されていません。.env を確認してください。")
        return

    ensure_session_state()

    if not has_log_consent():
        if st.session_state.consent_status == "declined":
            show_consent_declined_screen()
        else:
            show_consent_screen()
        return

    render_chat()

    user_message = st.chat_input("メッセージを入力してください")
    if user_message:
        st.session_state.messages.append({"role": "user", "content": user_message})
        ai_reply = generate_ai_reply(st.session_state.messages)
        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
        st.rerun()

    if st.session_state.get("is_processing", False):
        st.info("分析中です。しばらくお待ちください。")
        try:
            with st.spinner("分析中です... 少々お待ちください。"):
                st.session_state.analysis_result = analyze_user(st.session_state.messages)
            if st.session_state.analysis_result is not None:
                st.session_state.match_result = run_matching()
        except Exception as e:
            write_error_log("analysis_processing_exception", str(e))
        finally:
            st.session_state.is_processing = False
        st.rerun()
    else:
        if st.session_state.get("last_analysis_error") and not st.session_state.analysis_result:
            st.error("分析結果を取得できませんでした。もう一度お試しください。")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("分析してマッチングする", key="analyze_and_match"):
                user_messages = [
                    m for m in st.session_state.messages
                    if m.get("role") == "user" and m.get("content", "").strip()
                ]
                if len(user_messages) < 3:
                    st.warning("もう少し会話してから分析すると、より自然なマッチングになります。目安は3往復以上です。")
                else:
                    st.session_state.is_processing = True
                    st.rerun()
        with col2:
            if st.button("最初からやり直す", key="restart_during_chat"):
                handle_restart()

    if st.session_state.analysis_result:
        st.markdown("---")
        st.subheader("あなたの分析結果")
        analysis = st.session_state.analysis_result
        st.markdown(f"**性格傾向:** {analysis.get('personality','-')}")
        st.markdown(f"**大切にしている価値観:** {analysis.get('values','-')}")
        st.markdown(f"**隠れた欲求:** {analysis.get('hidden_needs','-')}")
        st.markdown(f"**会話スタイル:** {analysis.get('communication_style','-')}")
        st.markdown(f"**相性が良い相手像:** {analysis.get('ideal_partner_type','-')}")
        st.markdown(f"**一言要約:** {analysis.get('summary','-')}")
        st.info("💡 この分析はあなたの会話内容に基づいています。より深い対話でより正確な分析が可能です。")

    if st.session_state.match_result:
        st.markdown("---")
        st.subheader("マッチング結果")
        match = st.session_state.match_result
        candidate = match["matched_candidate"]
        st.markdown(f"**名前:** {candidate.get('name','-')} ({candidate.get('age','-')}歳)")
        st.markdown(f"**説明:** {candidate.get('description','-')}")
        st.markdown(f"**相性タイプ:** {match.get('match_label','-')}")
        st.success(f"**この候補者との相性ポイント:** {match.get('match_reason','-')}")
        st.warning(f"**注意点:** {match.get('possible_concern','-')}")
        st.info(f"**おすすめの最初のメッセージ:** {match.get('recommended_first_message','-')}")

        if st.session_state.top_match_candidates:
            other_candidates = [item for item in st.session_state.top_match_candidates[1:3] if item.get('candidate')]
            if other_candidates:
                st.markdown("---")
                st.markdown("**他にも相性が近かった候補者:**")
                analysis = st.session_state.analysis_result or {}
                for idx, item in enumerate(other_candidates, start=2):
                    c = item['candidate']
                    other_name = c.get('name', '未設定')
                    reason = generate_short_candidate_reason(analysis, c)
                    st.write(f"**{idx}位: {other_name}**")
                    st.caption(reason)

        st.markdown("---")
        st.caption("このマッチングはAIによる分析に基づいています。実際の相性は対話を通じて確かめてください。")

    if st.session_state.after_match_support:
        st.markdown("---")
        st.subheader("マッチ後支援")
        support = st.session_state.after_match_support

        render_support_field("今日送る一言", support.get('first_message_today', '-'))
        render_support_field("3日以内に聞く質問", support.get('question_in_3days', '-'))
        render_support_field("避けたほうがいい一言", support.get('avoid_phrase', '-'))
        render_support_field("返信が遅いときの対応", support.get('slow_reply_action', '-'))

    if st.session_state.match_result and not st.session_state.get("is_processing", False):
        st.markdown("---")
        fin_col1, fin_col2 = st.columns(2)
        with fin_col1:
            if st.button("最初からやり直す", key="restart_after_analysis_v003"):
                handle_restart_after_analysis()
        with fin_col2:
            if st.button("終わる", key="finish_after_analysis_v003"):
                handle_finish()

    with st.expander("デバッグ情報（開発用）", expanded=False):
        st.write("messages:", st.session_state.messages)
        st.write("last_analysis_response:", st.session_state.last_analysis_response)
        st.write("last_analysis_error:", st.session_state.last_analysis_error)
        st.write("---")
        st.write("【マッチング詳細】")
        st.write("selected_candidate_debug:", st.session_state.selected_candidate_debug)
        st.write("match_details_raw_response:", st.session_state.match_details_raw_response)
        st.write("match_details_error:", st.session_state.match_details_error)
        st.write("---")
        st.write("last_match_response:", st.session_state.last_match_response)
        st.write("last_match_error:", st.session_state.last_match_error)
        st.write("last_after_match_support_response:", st.session_state.last_after_match_support_response)
        st.write("last_after_match_support_error:", st.session_state.last_after_match_support_error)
        st.write("last_reply_finish_reason:", st.session_state.last_reply_finish_reason)
        st.write("top_match_candidates:", st.session_state.top_match_candidates)


if __name__ == "__main__":
    main()
