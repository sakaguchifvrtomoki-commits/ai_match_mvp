import base64
import datetime
import html as html_lib
import json
import math
import os
import traceback
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv
from googleapiclient.http import MediaFileUpload
from openai import OpenAI

load_dotenv()

APP_VERSION = "0.0.4"

GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeEl3FGWUk_-B7CtGLBOq1YNeeRNcClNibd-8ikF_Weh6rE9A/viewform"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
GOOGLE_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_openai_client():
    if not OPENAI_API_KEY:
        return None
    return OpenAI(api_key=OPENAI_API_KEY)


@st.cache_data
def get_image_base64(relative_path: str) -> str:
    try:
        path = Path(__file__).parent / relative_path
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""


def inject_custom_css():
    bg_b64 = get_image_base64("assets/fairies_ai_BG.png")
    btn_b64 = get_image_base64("assets/fairies_ai_button.png")

    bg_css = (
        f"url('data:image/png;base64,{bg_b64}')"
        if bg_b64
        else "linear-gradient(135deg, #e8f4fd 0%, #c8dff5 100%)"
    )
    btn_css = f"url('data:image/png;base64,{btn_b64}')" if btn_b64 else ""

    st.markdown(f"""
<style>
/* ===== 背景 ===== */
.stApp {{
    background-image: {bg_css};
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    background-repeat: no-repeat;
}}
.stApp > .main,
.stApp .main > div,
.block-container,
.stMainBlockContainer {{
    background: transparent !important;
    background-color: transparent !important;
}}
header[data-testid="stHeader"] {{
    background: transparent !important;
    background-color: transparent !important;
}}
[data-testid="stDecoration"] {{
    display: none !important;
}}

/* ===== フェアリーズタイトル ===== */
.fairies-header {{
    text-align: center;
    padding: 10px 0 16px 0;
}}
.fairies-header h1 {{
    font-size: 32px;
    font-weight: 700;
    color: #fff;
    text-shadow: 0 2px 8px rgba(0,0,0,0.45), 0 1px 2px rgba(0,0,0,0.3);
    margin: 0 0 4px 0;
    letter-spacing: 0.05em;
}}
.fairies-header .ver-badge {{
    display: inline-block;
    font-size: 11px;
    color: rgba(255,255,255,0.88);
    background: rgba(0,0,0,0.22);
    border-radius: 10px;
    padding: 2px 9px;
    letter-spacing: 0.06em;
}}

/* ===== チャット吹き出しコンテナ ===== */
/* ===== チャット画面 3往復案内 ===== */
.chat-guide-note {{
    background: rgba(255,255,255,0.82);
    border-left: 3px solid #7bafd4;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    color: #1a3570;
    margin-bottom: 8px;
    line-height: 1.55;
}}

.chat-container {{
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 8px 4px;
    width: 100%;
    box-sizing: border-box;
    overflow-x: hidden;
}}

/* ===== AI吹き出し（左） ===== */
.chat-row-ai {{
    display: flex;
    flex-direction: row;
    align-items: flex-end;
    gap: 8px;
    max-width: 100%;
}}
.ai-icon {{
    width: 40px;
    height: 40px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
    border: 2px solid rgba(255,255,255,0.75);
    box-shadow: 0 1px 4px rgba(0,0,0,0.18);
}}
.bubble-ai {{
    background: rgba(245, 250, 255, 0.93);
    color: #2c2c2c;
    border-radius: 4px 18px 18px 18px;
    padding: 10px 14px;
    max-width: 80%;
    font-size: 15px;
    line-height: 1.65;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    word-break: break-word;
    white-space: pre-wrap;
}}

/* ===== ユーザー吹き出し（右） ===== */
.chat-row-user {{
    display: flex;
    flex-direction: row-reverse;
    align-items: flex-end;
    gap: 8px;
    max-width: 100%;
}}
.bubble-user {{
    background: rgba(162, 214, 248, 0.92);
    color: #1a1a2e;
    border-radius: 18px 4px 18px 18px;
    padding: 10px 14px;
    max-width: 80%;
    font-size: 15px;
    line-height: 1.65;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    word-break: break-word;
    white-space: pre-wrap;
}}

/* ===== 送信ボタン（画像スタイル） ===== */
[data-testid="stChatInputSubmitButton"],
[data-testid="stChatInputSubmitButton"] button {{
    background-image: {btn_css};
    background-size: 80%;
    background-repeat: no-repeat;
    background-position: center;
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    width: 46px !important;
    height: 46px !important;
    min-height: 46px !important;
    padding: 0 !important;
    border-radius: 50% !important;
}}
[data-testid="stChatInputSubmitButton"] svg,
[data-testid="stChatInputSubmitButton"] button svg {{
    display: none !important;
}}

/* ===== チャット入力フォーム（st.form方式） ===== */

/* フォーム枠・背景を消す */
[data-testid="stForm"] {{
    border: none !important;
    padding: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
}}

/* stVerticalBlock を flex row で横並び1行に */
[data-testid="stForm"] [data-testid="stVerticalBlock"] {{
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    gap: 8px !important;
    width: 100% !important;
    box-sizing: border-box !important;
}}

/* 入力補助テキスト（Press Enter to submit form）を非表示 */
[data-testid="InputInstructions"] {{
    display: none !important;
}}

/* テキストエリアが残り幅を使う */
[data-testid="stForm"] [data-testid="stTextArea"] {{
    flex: 1 1 auto !important;
    min-width: 0 !important;
    margin-bottom: 0 !important;
}}
[data-testid="stForm"] [data-testid="stTextArea"] textarea {{
    border-radius: 20px !important;
    background: rgba(255,255,255,0.88) !important;
    border: 1px solid rgba(100,160,220,0.35) !important;
    padding-left: 14px !important;
    padding-right: 12px !important;
    font-size: 15px !important;
    width: 100% !important;
    min-width: 0 !important;
    box-sizing: border-box !important;
    resize: none !important;
    line-height: 1.5 !important;
}}

/* 送信ボタンを固定幅・画像化 */
[data-testid="stForm"] [data-testid="stFormSubmitButton"] {{
    flex: 0 0 48px !important;
    width: 48px !important;
    min-width: 48px !important;
    margin-bottom: 0 !important;
}}
[data-testid="stFormSubmitButton"] button {{
    background-image: {btn_css};
    background-size: 80% !important;
    background-repeat: no-repeat !important;
    background-position: center !important;
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    width: 48px !important;
    height: 48px !important;
    min-height: 48px !important;
    padding: 0 !important;
    border-radius: 50% !important;
    color: transparent !important;
}}
[data-testid="stFormSubmitButton"] button p,
[data-testid="stFormSubmitButton"] button [data-testid="stMarkdownContainer"],
[data-testid="stFormSubmitButton"] button svg {{
    display: none !important;
}}

/* ===== 結果カード（白背景） ===== */
.result-card {{
    background: rgba(255, 255, 255, 0.96);
    border-radius: 14px;
    padding: 18px 20px;
    margin: 14px 0;
    box-shadow: 0 3px 12px rgba(0,0,0,0.12);
    color: #2c2c2c;
}}
.result-card-title {{
    font-size: 17px;
    font-weight: 700;
    color: #1a3a5c;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 2px solid rgba(100,160,220,0.3);
}}
.result-card p {{
    margin: 6px 0;
    line-height: 1.65;
    font-size: 14px;
    color: #2c2c2c;
}}
.result-card ul {{
    margin: 4px 0 8px 0;
    padding-left: 20px;
    font-size: 14px;
    color: #2c2c2c;
}}
.result-label {{
    font-weight: 600;
    color: #2c5f8a;
    margin-right: 4px;
}}
.result-note {{
    margin-top: 12px !important;
    padding: 8px 12px !important;
    background: rgba(100,160,220,0.12);
    border-radius: 8px;
    font-size: 13px;
    color: #555 !important;
}}
.result-success {{
    background: rgba(50,200,100,0.1);
    border-left: 3px solid #2ea85c;
    padding: 8px 12px;
    border-radius: 0 8px 8px 0;
    margin: 8px 0;
    font-size: 14px;
    line-height: 1.65;
    color: #1a3a1a;
}}
.result-warning {{
    background: rgba(255,200,50,0.12);
    border-left: 3px solid #d49000;
    padding: 8px 12px;
    border-radius: 0 8px 8px 0;
    margin: 8px 0;
    font-size: 14px;
    line-height: 1.65;
    color: #3a2a00;
}}
.result-info {{
    background: rgba(100,160,220,0.12);
    border-left: 3px solid #5b9bd5;
    padding: 8px 12px;
    border-radius: 0 8px 8px 0;
    margin: 8px 0;
    font-size: 14px;
    line-height: 1.65;
    color: #0a2a4a;
}}
.result-divider {{
    border: none;
    border-top: 1px solid rgba(100,160,220,0.2);
    margin: 12px 0;
}}

/* ===== 背景上テキスト可読性（白縁取り: -webkit-text-stroke方式） ===== */
.stApp p, .stApp li,
.stApp h2, .stApp h3,
.stApp label,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {{
    color: #111 !important;
    -webkit-text-stroke: 4px rgba(255, 255, 255, 0.9);
    paint-order: stroke fill;
    text-shadow: none !important;
}}
/* カード内・吹き出し内はリセット */
.result-card p, .result-card li, .result-card h2, .result-card h3,
.result-card span, .result-card strong, .result-card div {{
    color: inherit !important;
    -webkit-text-stroke: 0 !important;
    paint-order: normal !important;
    text-shadow: none !important;
}}
.bubble-ai, .bubble-user {{
    -webkit-text-stroke: 0 !important;
    paint-order: normal !important;
    text-shadow: none !important;
}}

/* ===== 横スクロール防止（全幅） ===== */
html, body {{
    overflow-x: hidden !important;
    max-width: 100% !important;
}}
.stApp {{
    overflow-x: hidden !important;
}}
* {{
    box-sizing: border-box;
}}

/* ===== スマホ・タブレット対応（768px以下） ===== */
@media (max-width: 768px) {{

    /* Streamlit デフォルト余白を削減 */
    .block-container,
    .stMainBlockContainer {{
        padding-left: 12px !important;
        padding-right: 12px !important;
        padding-top: 16px !important;
        padding-bottom: 80px !important;
        max-width: 100% !important;
    }}

    /* タイトル */
    .fairies-header h1 {{ font-size: 26px; }}
    .fairies-header {{ padding: 8px 0 12px 0; }}

    /* 吹き出し */
    .bubble-ai, .bubble-user {{
        font-size: 14px;
        max-width: 85%;
        padding: 9px 12px;
    }}
    .chat-row-ai, .chat-row-user {{ gap: 6px; }}
    .ai-icon {{ width: 36px; height: 36px; }}
    .chat-container {{ gap: 10px; padding: 6px 2px; }}

    /* 結果カード */
    .result-card {{
        padding: 14px 16px;
        margin: 10px 0;
        border-radius: 12px;
    }}
    .result-card p,
    .result-card ul,
    .result-card li {{
        font-size: 13px;
    }}
    .result-card-title {{ font-size: 15px; }}
    .result-success,
    .result-warning,
    .result-info {{
        font-size: 13px;
        padding: 7px 10px;
    }}
    .result-note {{ font-size: 12px; }}

    /* チャット入力欄（768px以下） */
    [data-testid="stForm"] [data-testid="stTextArea"] textarea {{
        font-size: 14px !important;
    }}
    [data-testid="stForm"] [data-testid="stFormSubmitButton"] {{
        flex: 0 0 44px !important;
        width: 44px !important;
        min-width: 44px !important;
    }}
    [data-testid="stFormSubmitButton"] button {{
        width: 44px !important;
        height: 44px !important;
        min-height: 44px !important;
    }}
}}

/* ===== スマホ専用（480px以下） ===== */
@media (max-width: 480px) {{

    /* さらに余白を削減 */
    .block-container,
    .stMainBlockContainer {{
        padding-left: 8px !important;
        padding-right: 8px !important;
        padding-top: 12px !important;
    }}

    /* タイトル */
    .fairies-header h1 {{ font-size: 22px; letter-spacing: 0.02em; }}
    .fairies-header .ver-badge {{ font-size: 10px; }}

    /* 吹き出し */
    .bubble-ai, .bubble-user {{
        font-size: 13px;
        max-width: 88%;
        padding: 8px 10px;
        line-height: 1.6;
    }}
    .ai-icon {{ width: 32px; height: 32px; }}

    /* 結果カード */
    .result-card {{
        padding: 12px 13px;
        border-radius: 10px;
        margin: 8px 0;
    }}
    .result-card p,
    .result-card ul,
    .result-card li {{
        font-size: 12px;
    }}
    .result-card-title {{ font-size: 14px; margin-bottom: 10px; }}
    .result-success,
    .result-warning,
    .result-info {{
        font-size: 12px;
        padding: 6px 9px;
    }}

    /* チャット入力欄（480px以下） */
    [data-testid="stForm"] [data-testid="stVerticalBlock"] {{
        gap: 6px !important;
    }}
    [data-testid="stForm"] [data-testid="stTextArea"] textarea {{
        font-size: 13px !important;
        padding-left: 12px !important;
    }}
    [data-testid="stForm"] [data-testid="stFormSubmitButton"] {{
        flex: 0 0 40px !important;
        width: 40px !important;
        min-width: 40px !important;
    }}
    [data-testid="stFormSubmitButton"] button {{
        width: 40px !important;
        height: 40px !important;
        min-height: 40px !important;
    }}
        /* Streamlit Cloud 右下ロゴと重ならないように下部バーの右端を空ける */
    .fairies-bottom-bar {{
        padding-right: 120px !important;
    }}

    .bottom-bar-btn {{
        font-size: 11px !important;
    }}
}}

/* スマホ下部バー: 分析後の専用トリガーボタンを視覚的に非表示
   height:0 + overflow:hidden で折りたたみ、DOM には残して JS の .click() が届く */
[data-testid="stMarkdownContainer"]:has(.mobile-post-triggers) ~ [data-testid="stButton"] {{
    height: 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
    margin: 0 !important;
    padding: 0 !important;
}}

/* ===== スマホ下部固定バー ===== */
.fairies-bottom-bar {{
    display: none;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 56px;
    padding-right: 84px;
    background: rgba(255, 255, 255, 0.97);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-top: 1.5px solid rgba(100, 160, 220, 0.45);
    z-index: 2147483647 !important;
    flex-direction: row;
    align-items: stretch;
    box-shadow: 0 -3px 14px rgba(0,0,0,0.18);
    box-sizing: border-box;
    overflow: hidden;
}}
.fairies-bottom-bar * {{
    -webkit-text-stroke: 0 !important;
    paint-order: normal !important;
    text-shadow: none !important;
    box-sizing: border-box;
}}
.bottom-bar-kb {{
    flex: 0 0 54px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    border-right: 1.5px solid rgba(100, 160, 220, 0.4);
    -webkit-tap-highlight-color: transparent;
    user-select: none;
}}
.bottom-bar-kb img {{
    width: 26px;
    height: 26px;
    object-fit: contain;
    opacity: 0.88;
    pointer-events: none;
}}
.bottom-bar-actions {{
    flex: 1 1 auto;
    display: flex;
    flex-direction: row;
    align-items: stretch;
    min-width: 0;
}}
.bottom-bar-btn {{
    flex: 1 1 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #1a3570 !important;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    border: none;
    background: transparent;
    padding: 4px 2px;
    text-align: center;
    line-height: 1.3;
    -webkit-tap-highlight-color: transparent;
    user-select: none;
    min-width: 0;
    overflow: hidden;
}}
.bottom-bar-btn:active {{
    background: rgba(100, 160, 220, 0.18);
}}
.bottom-bar-btn + .bottom-bar-btn {{
    border-left: 1.5px solid rgba(100, 160, 220, 0.4);
}}
.bottom-bar-btn.wide {{
    flex: 1.7 1 0;
}}
.bottom-bar-btn.narrow {{
    flex: 0.75 1 0;
}}
@media (max-width: 768px) {{
    .fairies-bottom-bar {{ display: flex !important; }}
    /* 下部バー分の余白をコンテンツ最下部に確保 */
    .main .block-container {{
        padding-bottom: 72px !important;
    }}
    /* PC版ボタングループをスマホで非表示
       visibility:hidden にすることで DOM に残し、JS の clickNative() が動作する */
    [data-testid="stMarkdownContainer"]:has(.pc-only-btns-chat) + [data-testid="stHorizontalBlock"],
    [data-testid="stMarkdownContainer"]:has(.pc-only-btns-chat) + [data-testid="stColumns"],
    [data-testid="stMarkdownContainer"]:has(.pc-only-btns-post) ~ [data-testid="stMarkdownContainer"]:has(> hr),
    [data-testid="stMarkdownContainer"]:has(.pc-only-btns-post) ~ [data-testid="stHorizontalBlock"],
    [data-testid="stMarkdownContainer"]:has(.pc-only-btns-post) ~ [data-testid="stColumns"] {{
        visibility: hidden !important;
        height: 0 !important;
        min-height: 0 !important;
        overflow: hidden !important;
        margin: 0 !important;
        padding: 0 !important;
    }}

}}
/* ===== Streamlit Cloud 標準UIの非表示 ===== */
#MainMenu,
footer,
header,
.stDeployButton,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stHeader"] {{
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
}}
</style>
""", unsafe_allow_html=True)


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

def get_google_drive_service():
    """Streamlit Secrets のOAuth情報から Google Drive API クライアントを作る。"""
    try:
        if "google_oauth" not in st.secrets:
            st.session_state.last_drive_upload_error = "google_oauth が Streamlit Secrets に設定されていません。"
            write_error_log("google_drive_oauth_missing", "google_oauth is missing in Streamlit Secrets")
            return None

        oauth = st.secrets["google_oauth"]

        creds = Credentials(
            token=None,
            refresh_token=oauth["refresh_token"],
            token_uri=oauth.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=oauth["client_id"],
            client_secret=oauth["client_secret"],
            scopes=GOOGLE_DRIVE_SCOPES,
        )

        creds.refresh(Request())

        return build("drive", "v3", credentials=creds)

    except Exception as e:
        st.session_state.last_drive_upload_error = f"Google Drive OAuth認証に失敗しました: {e}"
        write_error_log("google_drive_oauth_failed", str(e))
        return None


def _escape_drive_query_text(text: str) -> str:
    """Google Drive API の query 用にファイル名を簡易エスケープする。"""
    return str(text).replace("\\", "\\\\").replace("'", "\\'")


def upload_file_to_google_drive(local_path):
    """指定されたローカルファイルをGoogle Driveの指定フォルダへアップロードする。

    同名ファイルがDriveフォルダ内にある場合は更新し、なければ新規作成する。
    失敗してもアプリ本体は止めない。
    """
    try:
        folder_id = st.secrets.get("GOOGLE_DRIVE_FOLDER_ID", "")
        if not folder_id:
            st.session_state.last_drive_upload_error = "GOOGLE_DRIVE_FOLDER_ID が設定されていません。"
            write_error_log("google_drive_folder_id_missing", "GOOGLE_DRIVE_FOLDER_ID is missing")
            return None

        local_path = Path(local_path)
        if not local_path.exists():
            st.session_state.last_drive_upload_error = f"アップロード対象ファイルが存在しません: {local_path}"
            write_error_log("google_drive_upload_file_missing", str(local_path))
            return None

        service = get_google_drive_service()
        if service is None:
            return None

        filename = local_path.name
        escaped_name = _escape_drive_query_text(filename)

        query = (
            f"name = '{escaped_name}' "
            f"and '{folder_id}' in parents "
            f"and trashed = false"
        )

        existing = service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name, webViewLink)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        media = MediaFileUpload(
            str(local_path),
            mimetype="text/markdown",
            resumable=False,
        )

        files = existing.get("files", [])
        if files:
            file_id = files[0]["id"]
            result = service.files().update(
                fileId=file_id,
                media_body=media,
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            ).execute()
            action = "updated"
        else:
            metadata = {
                "name": filename,
                "parents": [folder_id],
                "mimeType": "text/markdown",
            }
            result = service.files().create(
                body=metadata,
                media_body=media,
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            ).execute()
            action = "created"

        st.session_state.last_drive_upload_response = result
        st.session_state.last_drive_upload_error = None

        write_debug_log("google_drive_upload_finished", {
            "level": "INFO",
            "message": "Google Driveへのログアップロードが完了しました",
            "action": action,
            "file_name": result.get("name"),
            "file_id": result.get("id"),
            "webViewLink": result.get("webViewLink"),
        })

        return result

    except Exception as e:
        st.session_state.last_drive_upload_error = str(e)
        write_error_log("google_drive_upload_failed", str(e), {
            "local_path": str(local_path),
        })
        return None

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

        # Streamlit Cloud上のファイルは永続保存として信用しにくいため、
        # 同じMarkdownログをGoogle Driveにも保存する。
        upload_file_to_google_drive(log_path)

    except Exception as e:
        write_error_log("session_markdown_save_failed", str(e))
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
    st.markdown(
        '<div class="result-card" style="margin-bottom:16px; background:rgba(255,255,255,0.55);">'
        'このアプリは、AIとチャットすることであなたの性格や価値観を分析し、'
        'それをもとに一人の人物（架空）とマッチングするアプリです。'
        '</div>',
        unsafe_allow_html=True,
    )
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
    st.write("ログは、開発者が管理するGoogle Driveにも保存されます。")
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


def show_survey_screen():
    st.markdown(
        '<div style="text-align:center; padding: 32px 0 16px 0;">'
        '<p style="font-size:22px; font-weight:700; color:#fff; text-shadow:0 2px 8px rgba(0,0,0,0.4);">'
        'ご利用ありがとうございました</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="result-card">'
        '<p style="margin-bottom:8px;">今後の改善のため、1〜2分ほどのアンケートにご協力ください。</p>'
        '<p style="color:#555; font-size:13px; margin-bottom:12px;">回答は開発・検証目的でのみ使用します。</p>'
        f'<p style="font-size:12px; color:#888; margin:0;">うまく開かない場合は'
        f'<a href="{GOOGLE_FORM_URL}" target="_blank" rel="noopener noreferrer">'
        f'こちら</a>からどうぞ。</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.link_button(
        "アンケートに回答する",
        GOOGLE_FORM_URL,
        use_container_width=True,
    )

    st.caption("アンケート回答後、このページに戻って「回答後、終了する」を押してください。")

    if st.button("回答後、終了する", key="finish_after_survey", use_container_width=True):
        for key in ["show_survey_screen", "consent_status", "log_consent", "consented_at"]:
            st.session_state.pop(key, None)
        st.rerun()
    if st.button("回答せずに終了する", key="skip_survey", use_container_width=True):
        for key in ["show_survey_screen", "consent_status", "log_consent", "consented_at"]:
            st.session_state.pop(key, None)
        st.rerun()


def _reset_chat_state():
    st.session_state.is_processing = False
    st.session_state.analyze_insufficient_msg = None
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
    # ログ保存は必ず先に実行
    save_session_markdown_log(session_status="completed", end_reason="user_clicked_finish")

    # チャット・分析・マッチング関連をリセット（consent_status は show_survey_screen 表示のために残す）
    for key in [
        "session_id", "session_started_at", "session_log_path",
        "messages", "analysis_result", "match_result", "after_match_support",
        "top_match_candidates", "last_analysis_response", "last_analysis_error",
        "last_match_response", "last_match_error", "match_details_raw_response",
        "match_details_error", "selected_candidate_debug",
        "last_after_match_support_response", "last_after_match_support_error",
        "last_reply_finish_reason", "analyze_insufficient_msg", "is_processing",
    ]:
        st.session_state.pop(key, None)

    st.session_state.show_survey_screen = True
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


def handle_analyze_request():
    """分析開始の共通処理。PC版ボタンとスマホ下部バー（clickNative経由）の両方から呼ばれる。
    会話数が不足している場合は session_state に案内メッセージを保存して終了する。
    十分な場合は is_processing を立てて rerun する。
    """
    user_messages = [
        m for m in st.session_state.messages
        if m.get("role") == "user" and m.get("content", "").strip()
    ]
    if len(user_messages) < 3:
        st.session_state.analyze_insufficient_msg = (
            "もう少し会話してから分析すると、より自然なマッチングになります。目安は3往復以上です。"
        )
        st.rerun()
    else:
        st.session_state.analyze_insufficient_msg = None
        st.session_state.is_processing = True
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
    if "analyze_insufficient_msg" not in st.session_state:
        st.session_state.analyze_insufficient_msg = None
    if "last_drive_upload_response" not in st.session_state:
        st.session_state.last_drive_upload_response = None
    if "last_drive_upload_error" not in st.session_state:
        st.session_state.last_drive_upload_error = None
    if "show_survey_screen" not in st.session_state:
        st.session_state.show_survey_screen = False


def render_chat():
    icon_b64 = get_image_base64("assets/fairies_ai_icon.png")
    icon_src = f"data:image/png;base64,{icon_b64}" if icon_b64 else ""

    rows = []
    for msg in st.session_state.messages:
        role = msg.get("role", "")
        content = html_lib.escape(msg.get("content", "")).replace("\n", "<br>")
        if role in ("assistant", "ai"):
            icon_tag = (
                f'<img src="{icon_src}" class="ai-icon" alt="Fairies AI">'
                if icon_src
                else '<div class="ai-icon" style="background:#c8def5;"></div>'
            )
            rows.append(
                f'<div class="chat-row-ai">'
                f'{icon_tag}'
                f'<div class="bubble-ai">{content}</div>'
                f'</div>'
            )
        elif role == "user":
            rows.append(
                f'<div class="chat-row-user">'
                f'<div class="bubble-user">{content}</div>'
                f'</div>'
            )

    st.markdown(
        '<div class="chat-guide-note">'
        'より自然な分析のため、まずはAIと3往復以上会話してから「分析してマッチング」を押してください。'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="chat-container">' + "\n".join(rows) + "</div>",
        unsafe_allow_html=True,
    )


def render_mobile_bottom_bar():
    """スマホ下部固定バー。HTML div + position:fixed で画面下部に配置。
    表示文言と内部クリック対象を分離し、分析後ボタンの誤クリックを防ぐ。
    """
    kb_b64 = get_image_base64("assets/fairies_ai_keyboard.png")
    kb_src = f"data:image/png;base64,{kb_b64}" if kb_b64 else ""
    kb_img = (
        f'<img src="{kb_src}" alt="KB">'
        if kb_src
        else '<span style="font-size:22px;color:#1a3570;">&#9000;</span>'
    )

    is_post = bool(st.session_state.get("match_result"))

    if is_post:
        btn1_display = "最初から<br>やり直す"
        btn1_target = "mobile_post_restart_trigger"
        btn2_display = "終わる"
        btn2_target = "mobile_post_finish_trigger"
    else:
        btn1_display = "分析して<br>マッチング"
        btn1_target = "分析してマッチングする"
        btn2_display = "やり直す"
        btn2_target = "最初からやり直す"

    bar_html = (
        '<div class="fairies-bottom-bar">'
        f'<div class="bottom-bar-kb fairies-bar-kb">{kb_img}</div>'
        '<div class="bottom-bar-actions">'
        f'<button class="bottom-bar-btn wide fairies-bar-btn1" type="button">{btn1_display}</button>'
        f'<button class="bottom-bar-btn narrow fairies-bar-btn2" type="button">{btn2_display}</button>'
        '</div>'
        '</div>'
    )
    st.markdown(bar_html, unsafe_allow_html=True)

    components.html(
        f"""
        <script>
        (function() {{
            var T1 = '{btn1_target}';
            var T2 = '{btn2_target}';
            var attempts = 0;
            var debounceTimer = null;

            function normalizeText(text) {{
                return (text || '').replace(/\\s+/g, '').trim();
            }}

            function clickNative(label) {{
                var p = window.parent.document;
                var target = normalizeText(label);
                var btns = p.querySelectorAll('[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button');

                for (var i = 0; i < btns.length; i++) {{
                    if (btns[i].closest('.fairies-bottom-bar')) {{
                        continue;
                    }}

                    var btnText = normalizeText(btns[i].textContent);
                    if (btnText === target) {{
                        btns[i].click();
                        return true;
                    }}
                }}

                return false;
            }}

            // PC版ボタン列をスマホで非表示（DOMには残してclickNative()が動作できるようにする）
            function hidePcBtns() {{
                var p = window.parent.document;
                if (window.parent.innerWidth > 768) return;
                var pcLabels = ['分析してマッチングする', '最初からやり直す', '終わる'];
                var blocks = p.querySelectorAll(
                    '[data-testid="stHorizontalBlock"], [data-testid="stColumns"]'
                );
                for (var i = 0; i < blocks.length; i++) {{
                    var block = blocks[i];
                    var btns = block.querySelectorAll('button');
                    var isPC = false;
                    for (var j = 0; j < btns.length; j++) {{
                        if (pcLabels.indexOf(btns[j].textContent.trim()) !== -1) {{
                            isPC = true;
                            break;
                        }}
                    }}
                    if (isPC) {{
                        block.style.visibility = 'hidden';
                        block.style.height = '0';
                        block.style.minHeight = '0';
                        block.style.overflow = 'hidden';
                        block.style.margin = '0';
                        block.style.padding = '0';
                    }}
                }}

                var mds = p.querySelectorAll('[data-testid="stMarkdownContainer"]');
                for (var i = 0; i < mds.length; i++) {{
                    var ch = mds[i].children;
                    if (ch.length === 1 && ch[0].tagName === 'HR') {{
                        mds[i].style.display = 'none';
                    }}
                }}
            }}

            // 分析後トリガーボタンを視覚的に非表示
            function hideTriggerBtns() {{
                var p = window.parent.document;
                var labels = [
                    'mobile_post_restart_trigger',
                    'mobile_post_finish_trigger'
                ];
                var allBtns = p.querySelectorAll('[data-testid="stButton"] button');

                for (var i = 0; i < allBtns.length; i++) {{
                    if (labels.indexOf(allBtns[i].textContent.trim()) !== -1) {{
                        var c = allBtns[i].closest('[data-testid="stButton"]');
                        if (c) {{
                            c.style.height = '0';
                            c.style.minHeight = '0';
                            c.style.overflow = 'hidden';
                            c.style.margin = '0';
                            c.style.padding = '0';
                            c.style.opacity = '0';
                            c.style.pointerEvents = 'none';
                        }}
                    }}
                }}
            }}

            function bindBarButtons() {{
                var p = window.parent.document;
                var bar = p.querySelector('.fairies-bottom-bar');
                if (!bar) return false;

                var b1 = bar.querySelector('.fairies-bar-btn1');
                var b2 = bar.querySelector('.fairies-bar-btn2');
                var kb = bar.querySelector('.fairies-bar-kb');

                if (b1) {{
                    b1.onclick = function() {{
                        clickNative(T1);
                    }};
                }}

                if (b2) {{
                    b2.onclick = function() {{
                        clickNative(T2);
                    }};
                }}

                if (kb) {{
                    kb.onclick = function() {{
                        var ta = p.querySelector('[data-testid="stTextArea"] textarea');
                        if (ta) {{
                            ta.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                            setTimeout(function() {{ ta.focus(); }}, 250);
                        }}
                    }};
                }}

                return true;
            }}

            function setup() {{
                var p = window.parent.document;
                var bar = p.querySelector('.fairies-bottom-bar');
                if (!bar) {{
                    if (attempts < 25) {{
                        attempts++;
                        setTimeout(setup, 200);
                    }}
                    return;
                }}

                hidePcBtns();
                hideTriggerBtns();
                bindBarButtons();

                var observer = new MutationObserver(function() {{
                    if (debounceTimer) clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(function() {{
                        hidePcBtns();
                        hideTriggerBtns();
                        bindBarButtons();
                    }}, 80);
                }});

                observer.observe(p.body, {{ childList: true, subtree: true }});
            }}

            setup();
        }})();
        </script>
        """,
        height=0,
    )

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
    st.set_page_config(page_title=f"フェアリーズ ver{APP_VERSION}", layout="centered")
    inject_custom_css()
    st.markdown(
        f'<div class="fairies-header">'
        f'<h1>フェアリーズ</h1>'
        f'<span class="ver-badge">ver{APP_VERSION}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not OPENAI_API_KEY:
        st.error("OPENAI_API_KEY が設定されていません。.env を確認してください。")
        return

    ensure_session_state()

    # 「終わる」押下後はアンケート案内画面を最優先表示（同意確認より前）
    if st.session_state.get("show_survey_screen"):
        show_survey_screen()
        return

    if not has_log_consent():
        if st.session_state.consent_status == "declined":
            show_consent_declined_screen()
        else:
            show_consent_screen()
        return

    render_mobile_bottom_bar()
    render_chat()

    with st.form(key="chat_form", clear_on_submit=True):
        typed = st.text_area(
            label="メッセージ入力",
            placeholder="メッセージを入力して、右の吹き出しで送信",
            label_visibility="collapsed",
            height=68,
        )
        submitted = st.form_submit_button("送信")

    if submitted and typed.strip():
        st.session_state.analyze_insufficient_msg = None
        st.session_state.messages.append({"role": "user", "content": typed})
        ai_reply = generate_ai_reply(st.session_state.messages)
        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
        st.rerun()

    if st.session_state.get("is_processing", False):
        st.info("分析中です。しばらくお待ちください。")
        try:
            with st.spinner("分析中です... 少々お待ちください。"):
                st.session_state.analysis_result = analyze_user(st.session_state.messages)
            if st.session_state.analysis_result is not None:
                st.session_state.analyze_insufficient_msg = None
                st.session_state.match_result = run_matching()
        except Exception as e:
            write_error_log("analysis_processing_exception", str(e))
        finally:
            st.session_state.is_processing = False
        st.rerun()
    else:
        if st.session_state.get("last_analysis_error") and not st.session_state.analysis_result:
            st.error("分析結果を取得できませんでした。もう一度お試しください。")
        # 会話数不足メッセージ：PC ボタンコンテナの外で表示するためスマホでも見える
        if st.session_state.get("analyze_insufficient_msg"):
            st.markdown(
                '<div class="result-card" style="margin-bottom:8px;">'
                '<p style="color:#1a3570;margin:0;">💬 '
                + html_lib.escape(st.session_state.analyze_insufficient_msg)
                + '</p></div>',
                unsafe_allow_html=True,
            )
        # PC版ボタン（スマホではCSS+JSで非表示、DOMには残してclickNative()が動作）
        st.markdown('<div class="pc-only-btns-chat"></div>', unsafe_allow_html=True)
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("分析してマッチングする", key="analyze_and_match"):
                handle_analyze_request()
        with col2:
            if st.button("最初からやり直す", key="restart_during_chat"):
                handle_restart()

    if st.session_state.analysis_result:
        analysis = st.session_state.analysis_result
        esc = lambda s: html_lib.escape(str(s or "-"))
        st.markdown(
            '<div class="result-card">'
            '<div class="result-card-title">あなたの分析結果</div>'
            f'<p><span class="result-label">性格傾向:</span> {esc(analysis.get("personality"))}</p>'
            f'<p><span class="result-label">大切にしている価値観:</span> {esc(analysis.get("values"))}</p>'
            f'<p><span class="result-label">隠れた欲求:</span> {esc(analysis.get("hidden_needs"))}</p>'
            f'<p><span class="result-label">会話スタイル:</span> {esc(analysis.get("communication_style"))}</p>'
            f'<p><span class="result-label">相性が良い相手像:</span> {esc(analysis.get("ideal_partner_type"))}</p>'
            f'<p><span class="result-label">一言要約:</span> {esc(analysis.get("summary"))}</p>'
            '<p class="result-note">💡 この分析はあなたの会話内容に基づいています。より深い対話でより正確な分析が可能です。</p>'
            '</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.match_result:
        match = st.session_state.match_result
        candidate = match["matched_candidate"]
        esc = lambda s: html_lib.escape(str(s or "-"))

        other_html = ""
        if st.session_state.top_match_candidates:
            other_candidates = [
                item for item in st.session_state.top_match_candidates[1:3]
                if item.get("candidate")
            ]
            if other_candidates:
                _analysis = st.session_state.analysis_result or {}
                items_html = ""
                for idx, item in enumerate(other_candidates, start=2):
                    c = item["candidate"]
                    items_html += (
                        f'<p><span class="result-label">{idx}位: {esc(c.get("name","未設定"))}（{esc(str(c.get("age","?")))}歳）</span>'
                        f'{esc(generate_short_candidate_reason(_analysis, c))}</p>'
                    )
                other_html = (
                    '<div class="result-divider"></div>'
                    '<p><span class="result-label">他にも相性が近かった候補者:</span></p>'
                    + items_html
                )

        st.markdown(
            '<div class="result-card">'
            '<div class="result-card-title">マッチング結果</div>'
            f'<p><span class="result-label">名前:</span> {esc(candidate.get("name"))}（{esc(str(candidate.get("age","?")))}歳）</p>'
            f'<p><span class="result-label">説明:</span> {esc(candidate.get("description"))}</p>'
            f'<p><span class="result-label">相性タイプ:</span> {esc(match.get("match_label"))}</p>'
            f'<div class="result-success"><strong>相性ポイント:</strong> {esc(match.get("match_reason"))}</div>'
            f'<div class="result-warning"><strong>注意点:</strong> {esc(match.get("possible_concern"))}</div>'
            f'<div class="result-info"><strong>おすすめの最初のメッセージ:</strong> {esc(match.get("recommended_first_message"))}</div>'
            + other_html
            + '<p class="result-note">このマッチングはAIによる分析に基づいています。実際の相性は対話を通じて確かめてください。</p>'
            '</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.after_match_support:
        support = st.session_state.after_match_support
        esc = lambda s: html_lib.escape(str(s or "-"))

        def _support_item(label, value):
            if isinstance(value, list):
                items = "".join(f"<li>{esc(i)}</li>" for i in value)
                return f'<p class="result-label">{label}</p><ul>{items}</ul>'
            return f'<p><span class="result-label">{label}:</span> {esc(str(value))}</p>'

        st.markdown(
            '<div class="result-card">'
            '<div class="result-card-title">マッチ後支援</div>'
            + _support_item("今日送る一言", support.get("first_message_today", "-"))
            + _support_item("3日以内に聞く質問", support.get("question_in_3days", "-"))
            + _support_item("避けたほうがいい一言", support.get("avoid_phrase", "-"))
            + _support_item("返信が遅いときの対応", support.get("slow_reply_action", "-"))
            + '</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.match_result and not st.session_state.get("is_processing", False):
        # PC版ボタン（スマホではCSS+JSで非表示、DOMには残してclickNative()が動作）
        st.markdown('<div class="pc-only-btns-post"></div>', unsafe_allow_html=True)
        st.markdown("---")
        fin_col1, fin_col2 = st.columns(2)
        with fin_col1:
            if st.button("最初からやり直す", key="restart_after_analysis_v003"):
                handle_restart_after_analysis()
        with fin_col2:
            if st.button("終わる", key="finish_after_analysis_v003"):
                handle_finish()
        # スマホ下部バー用隠れトリガーボタン（分析後）
        # clickNative() がこのラベルを検索して .click() する。
        # CSS で height:0/overflow:hidden に折りたたんで視覚的に非表示。
        st.markdown('<span class="mobile-post-triggers"></span>', unsafe_allow_html=True)
        if st.button("mobile_post_restart_trigger", key="mobile_post_restart"):
            handle_restart_after_analysis()
        if st.button("mobile_post_finish_trigger", key="mobile_post_finish"):
            handle_finish()

    # デバッグ情報（開発用）
    # PCでは折りたたみ表示、スマホではJSで非表示にする
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
        st.write("---")
        st.write("【Google Driveログ保存】")
        st.write("last_drive_upload_response:", st.session_state.last_drive_upload_response)
        st.write("last_drive_upload_error:", st.session_state.last_drive_upload_error)

    components.html(
        """
        <script>
        (function() {
            function hideDebugExpander() {
                var p = window.parent.document;

                // PC幅では表示したままにする
                if (window.parent.innerWidth > 768) {
                    return;
                }

                var targetText = 'デバッグ情報（開発用）';

                // Streamlit の expander は環境によって details だったり data-testid が変わるため複数候補を見る
                var candidates = p.querySelectorAll('details, [data-testid="stExpander"]');

                for (var i = 0; i < candidates.length; i++) {
                    var el = candidates[i];
                    if ((el.textContent || '').indexOf(targetText) !== -1) {
                        el.style.display = 'none';
                        el.style.height = '0';
                        el.style.minHeight = '0';
                        el.style.overflow = 'hidden';
                        el.style.margin = '0';
                        el.style.padding = '0';
                    }
                }

                // details / stExpander で見つからない場合の保険：
                // 見出しテキストを持つ要素から近いコンテナを折りたたむ
                var all = p.querySelectorAll('summary, button, [role="button"], [data-testid="stMarkdownContainer"]');

                for (var j = 0; j < all.length; j++) {
                    var node = all[j];
                    if ((node.textContent || '').indexOf(targetText) !== -1) {
                        var container =
                            node.closest('details') ||
                            node.closest('[data-testid="stExpander"]') ||
                            node.closest('[data-testid="stElementContainer"]');

                        if (container) {
                            container.style.display = 'none';
                            container.style.height = '0';
                            container.style.minHeight = '0';
                            container.style.overflow = 'hidden';
                            container.style.margin = '0';
                            container.style.padding = '0';
                        }
                    }
                }
            }

            hideDebugExpander();

            var p = window.parent.document;
            var timer = null;
            var observer = new MutationObserver(function() {
                if (timer) clearTimeout(timer);
                timer = setTimeout(hideDebugExpander, 100);
            });

            observer.observe(p.body, { childList: true, subtree: true });
        })();
        </script>
        """,
        height=0,
    )
    
if __name__ == "__main__":
    main()
