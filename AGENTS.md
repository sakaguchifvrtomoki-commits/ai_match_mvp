# Fairies 開発ルール

## 現在の開発対象

- 開発バージョンは `v0.2.2`、通常の開発ブランチは `feature/v0.2.2-fastapi` とする。
- Phase 1の4 Agent開発では、後述する `agent/*` ブランチを正式な例外として使用する。
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

## Phase 1の4 Agent運用

Git worktreeごとに担当ブランチを固定し、次の分担で作業する。

- `agent/backend`: `api/`、Python backend、Python tests
- `agent/flutter`: `flutter_app/`、Flutter tests
- `agent/test-review`: レビューとテストを中心に担当し、production codeは原則変更しない
- `agent/integration`: 各Agentのcommit統合、競合対応、全テスト、統合後レビュー

共通運用ルールは `docs/ai_development_team_rules.md` に従う。特に、各Agentは割り当てられたworktreeとbranchだけで作業し、担当外のproduction codeを変更しない。`reset`、`clean`、`rebase`、branch切り替えは禁止する。
