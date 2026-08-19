# Fairies 開発ルール

## 現在の開発対象

- 開発バージョンは `v0.2.2`、作業ブランチは `feature/v0.2.2-fastapi` とする。
- `v0.2.1` の既存Streamlit版を壊さず、Flutter向けFastAPIを段階的に追加する。
- APIは1本ずつ実装し、各APIの実装ごとにテストする。
- APIの詳細仕様は `docs/fairies_spec.md` を正とする。

## 責務分担

- FlutterはUI、画面状態、会話履歴を含む一時データを担当する。
- Python/FastAPIはAI通信、人物分析、マッチング、Fairyプロフィール処理、永続保存を担当する。
- FastAPIでは `st.session_state` を使用しない。必要な状態はリクエストで明示的に受け取る。
- 永続データは最終的にGoogle Driveを正本とし、一時データはFlutter側のユーザー端末で保持する。
- FastAPIは将来のクラウドデプロイを前提に実装する。

## 実装ルール

- 既存の人物分析、マッチング、プロフィールmerge/migrationロジックは可能な限り再利用する。
- Streamlit依存部分と再利用可能な業務ロジックを分離し、既存Streamlit版との互換性を維持する。
- セッションIDはAPI呼び出しごとに明示的に生成し、暗黙のセッション状態へ依存しない。
- エラー時もFlutter側の会話・画面状態を消さず、再試行可能にする。
- Google Driveからプロフィールを読み込めない場合、空プロフィールで上書きしない。
- `v0.2.2` ではプロフィールスキーマを変更せず、新しいmigrationを追加しない。既存のv0.2.1までのmigration機構を維持する。

## 対象APIと実装順

1. `POST /sessions`
2. `POST /chat`
3. `POST /match`
4. `POST /sessions/{session_id}/end`

各APIの実装前に仕様とテスト観点を確認し、無関係な変更を混ぜないこと。
