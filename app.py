import json
import math
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def get_openai_client():
    if not OPENAI_API_KEY:
        return None
    return OpenAI(api_key=OPENAI_API_KEY)


def load_candidates():
    path = Path(__file__).parent / "candidates.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def initial_question() -> str:
    return "あなたが最近、楽しかったことや少し気になっていることを教えてください。"


def ensure_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": initial_question()}]
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "match_result" not in st.session_state:
        st.session_state.match_result = None
    if "after_match_support" not in st.session_state:
        st.session_state.after_match_support = None
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


def analyze_user(chat_history):
    client = get_openai_client()
    if client is None:
        return None

    conversation = "\n".join(
        [f"[{msg['role']}]: {msg['content']}" for msg in chat_history]
    )
    prompt = (
        "あなたはユーザーの性格、価値観、本音を分析するアシスタントです。"
        " 以下の会話履歴から、JSON形式で分析結果を出力してください。"
        " JSONのキーは personality、values、hidden_needs、communication_style、ideal_partner_type、summary です。"
        " 各値は日本語で、断定調を避けて「〜かもしれません」「〜の可能性があります」を使ってください。"
        " 各項目について、会話履歴から具体的な例や引用を1-2つ含めて説明を充実させてください。"
        " 出力は必ずJSONのみでお願いします。\n\n"
        f"会話履歴:\n{conversation}\n"
    )
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "あなたは日本語で分析結果をJSONで出力するアシスタントです。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_completion_tokens=1200,  # 少し増やす
        )
        st.session_state.last_analysis_response = response.choices[0].message.content.strip()
        analysis = extract_json(st.session_state.last_analysis_response)
        if analysis is None:
            st.session_state.last_analysis_error = "JSON解析に失敗しました。"
        else:
            st.session_state.last_analysis_error = None
        return analysis
    except Exception as e:
        st.session_state.last_analysis_error = str(e)
        st.session_state.last_analysis_response = None
        return None


def build_profile_text(candidate):
    parts = [
        f"名前: {candidate['name']}",
        f"年齢: {candidate['age']}",
        f"性格: {candidate['personality']}",
        f"価値観: {candidate['values']}",
        f"趣味: {candidate['hobbies']}",
        f"会話スタイル: {candidate['communication_style']}",
        f"関係性スタイル: {candidate['relationship_style']}",
        f"説明: {candidate['description']}",
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


def choose_best_candidate(analysis, candidates):
    client = get_openai_client()
    if client is None or analysis is None:
        return None

    analysis_text = build_analysis_text(analysis)
    analysis_emb = get_embedding(client, analysis_text)
    best = None
    best_score = -1.0

    for candidate in candidates:
        candidate_text = build_profile_text(candidate)
        candidate_emb = get_embedding(client, candidate_text)
        score = cosine_similarity(analysis_emb, candidate_emb)
        if score > best_score:
            best_score = score
            best = candidate

    if best is None:
        return None

    return {
        "candidate": best,
        "similarity": best_score,
    }


def build_reason_prompt(analysis, candidate):
    """（旧実装は廃止。新しい build_match_details_prompt() を使用）"""
    return ""



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
        "match_reason": details.get("reason", ""),
        "possible_concern": details.get("caution", ""),
        "recommended_first_message": details.get("first_message", ""),
    }


def generate_match_details(analysis, candidate, conversation_summary=""):
    """
    マッチング詳細情報（reason, caution, first_message）を生成する。
    禁止文が含まれた場合は再生成。
    """
    client = get_openai_client()
    if client is None:
        return None
    
    prompt = build_match_details_prompt(analysis, candidate, conversation_summary)
    
    # 禁止文
    forbidden_phrases = [
        "この候補者はあなたの価値観や会話スタイルとよく合っている可能性があります",
        "違いがある場合は、お互いのペースを確認することが大切かもしれません",
        "最近のことや興味を持っていることについて気軽に話しかけてみましょう"
    ]
    
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
                max_completion_tokens=1200,  # 増やす
            )
            
            raw_response = response.choices[0].message.content.strip()
            st.session_state.match_details_raw_response = raw_response
            
            details = extract_json(raw_response)
            if details is None:
                st.session_state.match_details_error = f"JSON解析に失敗しました（試行 {attempt+1}/{max_retries}）"
                continue
            
            # 禁止文チェック
            has_forbidden = False
            for phrase in forbidden_phrases:
                if phrase in str(details.get('reason', '')) or phrase in str(details.get('caution', '')) or phrase in str(details.get('first_message', '')):
                    has_forbidden = True
                    st.session_state.match_details_error = f"禁止文が検出されました: {phrase}"
                    break
            
            if has_forbidden:
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
        f"名前: {candidate['name']}\n"
        f"年齢: {candidate['age']}\n"
        f"性格: {candidate['personality']}\n"
        f"価値観: {candidate['values']}\n"
        f"趣味: {candidate['hobbies']}\n"
        f"会話スタイル: {candidate['communication_style']}\n"
        f"関係性スタイル: {candidate['relationship_style']}\n"
        f"説明: {candidate['description']}\n\n"
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
    
    # ステップ1: 埋め込みベースで候補者を絞る
    match = choose_best_candidate(analysis, candidates)
    if match is None:
        st.session_state.last_match_error = "候補者を選出できませんでした。"
        return None
    
    # ステップ2: AIに詳細なマッチング理由を生成させる
    match_result = build_match_result(analysis, match["candidate"], match["similarity"])
    
    return match_result


def build_after_match_support_prompt(analysis, match_result):
    """マッチ後支援AIのプロンプトを構築する"""
    return (
        "あなたはAI分身マッチングのマッチ後支援アシスタントです。"
        " マッチ後に、2人の関係が続きやすくなるための支援方針を作成してください。\n\n"
        "以下のユーザー分析とマッチング結果をもとに、関係継続のための具体的な支援方針をJSON形式で出力してください。\n\n"
        "【ユーザー分析】\n"
        f"性格傾向: {analysis.get('personality','')}\n"
        f"価値観: {analysis.get('values','')}\n"
        f"隠れた欲求: {analysis.get('hidden_needs','')}\n"
        f"会話スタイル: {analysis.get('communication_style','')}\n"
        f"理想の相手像: {analysis.get('ideal_partner_type','')}\n"
        f"要約: {analysis.get('summary','')}\n\n"
        "【マッチ相手】\n"
        f"名前: {match_result['matched_candidate'].get('name','')}\n"
        f"性格: {match_result['matched_candidate'].get('personality','')}\n"
        f"価値観: {match_result['matched_candidate'].get('values','')}\n"
        f"会話スタイル: {match_result['matched_candidate'].get('communication_style','')}\n"
        f"関係性スタイル: {match_result['matched_candidate'].get('relationship_style','')}\n"
        f"相性スコア: {match_result['match_score']}/100\n\n"
        "【出力形式】\n"
        "JSONのみで、以下のキーを必ず含めてください。"
        " relationship_key_points(関係継続の重要ポイント)、"
        " first_week_approach(最初の1週間の接し方)、"
        " questions_to_ask(相手に投げるとよい問い 複数)、"
        " avoid_behaviors(避けたほうがよい対応)、"
        " deepening_themes(関係が深まりやすい会話テーマ 複数)、"
        " support_principle(支援方針・大事にすること)、"
        " support_type(支援タイプ: relationship_focus, change_tolerance, question_responsive, silence_tolerance, inner_sharing, ai_adaptive からいずれか複数)\n\n"
        "【重要な観点】\n"
        "- 単なる恋愛アドバイスではなく、長期的な関係継続を前提とする\n"
        "- 定期的な問いで関係を更新し、相互理解を深める視点を入れる\n"
        "- 相手に合う距離感を保ち、無理な連絡頻度を避ける\n"
        "- ユーザーが安心して関係を育てられる温度感で支援する\n"
        "- マッチ相手との具体的なマッチングポイントに基づいた支援を心がける"
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
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "あなたは日本語で丁寧に回答し、JSON形式で出力するアシスタントです。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_completion_tokens=1200,
        )
        st.session_state.last_after_match_support_response = response.choices[0].message.content.strip()
        support = extract_json(st.session_state.last_after_match_support_response)
        
        if support is None:
            st.session_state.last_after_match_support_error = "JSON解析に失敗しました。"
            return None
        
        st.session_state.last_after_match_support_error = None
        return support
        
    except Exception as e:
        st.session_state.last_after_match_support_error = str(e)
        st.session_state.last_after_match_support_response = None
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
    
    return match_result


def main():
    st.set_page_config(page_title="AI分身マッチングMVP", layout="centered")
    st.title("AI分身マッチングMVP")
    st.write(
        "AIとの対話を通じて、あなたの性格や価値観を分析し、相性のよさそうな候補者を1人紹介します。"
    )

    if not OPENAI_API_KEY:
        st.error("OPENAI_API_KEY が設定されていません。.env を確認してください。")
        return

    ensure_session_state()
    render_chat()

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

    user_message = st.chat_input("メッセージを入力してください")
    if user_message:
        st.session_state.messages.append({"role": "user", "content": user_message})
        ai_reply = generate_ai_reply(st.session_state.messages)
        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
        st.rerun()

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("分析してマッチングする"):
            if len(st.session_state.messages) <= 1:
                st.warning("まずはAIとの会話を少し進めてください。")
            else:
                with st.spinner("分析中です... 少々お待ちください。"):
                    st.session_state.analysis_result = analyze_user(st.session_state.messages)
                    st.session_state.match_result = run_matching()
                    if st.session_state.analysis_result is None:
                        st.error("分析結果を取得できませんでした。もう一度お試しください。")
    with col2:
        if st.button("最初からやり直す"):
            st.session_state.messages = [{"role": "assistant", "content": initial_question()}]
            st.session_state.analysis_result = None
            st.session_state.match_result = None
            st.session_state.after_match_support = None
            st.rerun()

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
        st.markdown(f"**相性スコア:** {match.get('match_score',0)} / 100")
        st.success(f"**なぜ相性が良いのか:** {match.get('match_reason','-')}")
        st.warning(f"**注意点:** {match.get('possible_concern','-')}")
        st.info(f"**おすすめの最初のメッセージ:** {match.get('recommended_first_message','-')}")
        st.markdown("---")
        st.caption("このマッチングはAIによる分析に基づいています。実際の相性は対話を通じて確かめてください。")

    if st.session_state.after_match_support:
        st.markdown("---")
        st.subheader("マッチ後支援")
        support = st.session_state.after_match_support
        
        render_support_field("関係継続の重要ポイント", support.get('relationship_key_points','-'))
        render_support_field("最初の1週間の接し方", support.get('first_week_approach','-'))
        render_support_field("相手に投げるとよい問い", support.get('questions_to_ask','-'))
        render_support_field("避けたほうがよい対応", support.get('avoid_behaviors','-'))
        render_support_field("関係が深まりやすい会話テーマ", support.get('deepening_themes','-'))
        render_support_field("支援方針・大事にすること", support.get('support_principle','-'))
        
        if support.get('support_type'):
            support_types = support.get('support_type')
            if isinstance(support_types, list):
                support_type_str = " / ".join(support_types)
            else:
                support_type_str = str(support_types)
            st.write(f"**支援タイプ:** {support_type_str}")


if __name__ == "__main__":
    main()
