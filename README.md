# AI分身マッチングMVP

AIとの会話を通じて、あなたの性格や価値観を分析し、相性の良さそうな候補者を1人紹介するローカルMVPです。

## 概要

- Streamlit で簡単なチャットUIを提供します。
- ユーザーと AI が会話を進めることで、性格や価値観を分析します。
- 事前に用意した候補者データから、最も相性の良い1人を提示します。
- データベースは使わず、ローカルの JSON ファイルを利用します。

## セットアップ

1. リポジトリをクローンまたはワークスペースに配置します。
2. Python 環境を用意します。
3. 依存パッケージをインストールします。

```bash
pip install -r requirements.txt
```

4. ルートに `.env` ファイルを作成し、以下の環境変数を設定します。

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-5.4-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

## 実行方法

```bash
streamlit run app.py
```

## 必要な環境変数

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_EMBEDDING_MODEL`

## 今後の改善案

- 会話履歴に対してより自然なチャットUIを追加する。
- 候補者の相性判定により高度なスコアリングや多角的なマッチングを導入する。
- 候補者プロフィールを事前に編集できる管理画面を追加する。
- 分析結果の説明をより詳細にし、ユーザーに選択肢を提示する。
- エラー処理やネットワーク障害時のリトライを強化する。
