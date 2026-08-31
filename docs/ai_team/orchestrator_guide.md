# Fairies Phase 2 Orchestrator Guide

## 目的と入力

司令塔は、人間から受け取った1つの開発ゴール、制約、期待する成果、明示された判断を入力とし、実行可能なTask Briefへ変換する。曖昧な仕様を補完せず、実装方法の細部は担当Agentに委ねる。

## 事前確認

1. 現在のbranch、`git status`、関連する履歴と既存実装を確認する。
2. `AGENTS.md` と `docs/ai_development_team_rules.md` を確認する。
3. APIや責務に関わるゴールでは `docs/fairies_spec.md` を正として、対象APIの契約、既存テスト、BackendとFlutterの境界を確認する。
4. ゴールと現状の差分、影響範囲、未確定事項を整理する。
5. Task BriefにBaseline commit SHA、参照する仕様書、対象セクションを記録する。

各 `RUN` Agentには、Worktree absolute path、Branch、Start commit SHA、RUN mode（`READ ONLY` または `WRITE`）を指定する。既定の作業場所は次のとおりとする。

| Agent | Worktree absolute path | Branch |
| --- | --- | --- |
| Backend | `C:\Users\sakag\other\fairies-backend` | `agent/backend` |
| Flutter | `C:\Users\sakag\other\fairies-flutter` | `agent/flutter` |
| Test/Review | `C:\Users\sakag\other\fairies-test` | `agent/test-review` |
| Integration | `C:\Users\sakag\other\fairies-integration` | `agent/integration` |
| Orchestrator（作業が必要な場合） | `C:\Users\sakag\other\fairies-orchestrator` | `agent/orchestrator` |

Agentは着手前に、指定されたworktree、branch、Start commit SHAが実際のGit状態と一致することを確認する。一致しない場合は着手せず、差異を報告する。

## Agentへの分解基準

- **Backend**: `api/`、Python業務ロジック、AI通信、プロフィール処理、永続保存、Python tests。
- **Flutter**: `flutter_app/` のUI、画面状態、一時データ、API client、Flutter tests。
- **Test/Review**: 仕様と実装のレビュー、独立したテスト観点、回帰確認。production codeは原則変更しない。
- **Integration**: 各commitの統合、競合対応、全テスト、統合後レビュー。未確定仕様の決定はしない。

ゴール達成に不要なAgentへ仕事を作らない。各Agentは `RUN` または `SKIP` とし、`SKIP` には短い理由を書く。

Integration Agentによる統合操作を除き、`RUN` となるBackend、Flutter、Test/Review、OrchestratorのAllowed Filesは相互に重複させない。Test/Review Agentがレビューだけを行う場合は `READ ONLY` とし、Allowed Filesを編集対象として持たせず、参照対象を別に記載する。

意図的に同じファイルを扱う必要がある場合は並列実行を禁止し、Task Briefに先行Agent、後続Agent、先行commit SHAを用いた後続Agentの開始条件、ファイル所有権の引き渡し条件を明記する。引き渡し後、先行Agentはそのファイルを変更しない。

## 依存関係と並列化

ファイル所有範囲が分離され、確定済みの契約を共有でき、片方の成果を入力にしないタスクは並列化できる。レビュー観点の準備も、対象仕様が確定していれば実装と並列化できる。

次の場合は順番を指定する。

- API契約が未確定: 人間の決定後、契約を一方または独立タスクで確定してからBackendとFlutterを実装する。
- 一方が生成・変更する契約、モデル、成果物を他方が利用する: 提供側を先行させる。
- 複数Agentが意図的に同じファイルを扱う: ファイル所有権を先行commit単位で引き渡してから後続Agentを開始する。
- Integrationや統合後テスト: 必要な実装commitとレビュー結果の後に行う。

## Acceptance Criteria Gate

- 各 `RUN` タスクには、結果を客観的に確認できるAcceptance Criteriaを必須とする。
- Acceptance Criteriaが空欄、未確定、または主観だけの場合はTask Briefを発行しない。
- Acceptance Criteriaが確定するまでAgentは着手しない。
- 確定に人間判断が必要な事項は `Human Decisions Required` へ戻す。
- 「良い感じ」など実機または人間の評価が必要なUX項目は、自動判定できるAcceptance Criteriaと `Human Verification` を分離する。

## 人間へ判断を戻す境界

次の変更や選択が必要な場合は、選択肢、影響、推奨案をTask Briefの `Human Decisions Required` に記載し、決定前の依存タスクを開始させない。

- プロダクト価値や要件の優先順位
- ユーザーに見えるUX、エラー時の挙動、データ消失に関わる挙動
- API契約、責務境界、後方互換性
- profile schema、保存方式、データ互換性
- migrationの追加または変更

命名、内部構造、局所的なアルゴリズムなど、契約や価値を変えない実装詳細は担当Agentに委ねる。

## 禁止事項と出力

- 司令塔自身はproduction codeを実装・変更しない。
- 司令塔自身はbranchのmergeや競合解決をしない。
- すべての依頼を機械的に4分割しない。
- 未確定仕様を推測で確定しない。

出力は常に `docs/ai_team/task_brief_template.md` のTask Brief形式に統一する。各担当がそのまま着手でき、Integrationが順序と成果物を検証できる具体性を持たせる。
