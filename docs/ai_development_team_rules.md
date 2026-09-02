# Fairies AI開発チーム運用ルール

## 体制と担当

Phase 1では、4つのGit worktreeとbranchを使って並行作業する。各Agentは割り当てられたworktreeとbranchだけで作業する。

| Branch | 担当 |
| --- | --- |
| `agent/backend` | `api/`、Python backend、Python tests |
| `agent/flutter` | `flutter_app/`、Flutter tests |
| `agent/test-review` | レビューとテスト。production codeは原則変更しない |
| `agent/integration` | commit統合、競合対応、全テスト、統合後レビュー |

通常の開発ブランチは `feature/v0.2.2-fastapi` とし、上記の `agent/*` branchはPhase 1の正式な例外とする。

## Phase 2の司令塔

Phase 2では既存の4 Agent体制を維持し、その前段に `agent/orchestrator` を追加する。司令塔はproduction codeの実装やmergeをせず、人間のゴールを実行可能なTask Briefへ分解する。不要なAgentは `SKIP` とする。

作業の流れは次のとおりとする。

`人間 → 司令塔 → Backend／Flutter／Test・Review → Integration → 人間`

司令塔の判断基準と出力形式は `docs/ai_team/orchestrator_guide.md` に従う。

## 作業ルール

- 担当外のproduction codeを変更しない。
- `reset`、`clean`、`rebase`、branch切り替えは禁止する。
- 実装Agentは作業終了時に自分のbranchへcommitする。
- Integration Agent以外は、他Agentのbranchをmergeしない。
- 成果物は、完全なcommit SHA、変更概要、テスト結果、既知の問題を添えて渡す。
- テストが失敗した場合は、仕様を変えずに直せる範囲で原因を調査し、修正後に再テストする。
- API契約、UX、プロフィールschema、保存方式、migration、互換性の変更が必要な場合は、独断で変更せず人間へ判断を戻す。
- 実Google Driveテストなど外部データを書き換えるテストは、人間の明示許可なしに実行しない。
- token、credential、秘密鍵などの秘密情報をcommitしない。

## Phase 3B WRITE Runtimeの限定例外

人間がraw-byte SHA-256で承認し、独立Test/ReviewがAPPROVEしたPhase 3B
Runtime Task Briefに限り、Backend／Flutter AgentへTask Brief記載の一時的所有権を
付与できる。Runtimeはworktree、branch、HEAD、clean state、physical path、approval
digestを各Agent起動直前にfail-closedで検証し、Allowed Files外を変更してはならない。

WRITE Agentは実装と指定testまでを担当し、stage／commit／mergeは行わない。変更は
binary-safe patch、content-addressed untracked bytes、Git/test evidence、検証済みreport
としてrepository外の安全なartifact directoryへ固定し、READ ONLY Test/Reviewへ配送する。
Test/ReviewのAPPROVEと`READY_FOR_PHASE3C`が揃うまで統合を開始しない。通常のPhase 1/2
commit handoff、担当範囲および禁止操作はこの将来Runtime例外によって変更されず、
既存作業を遡及的に正当化しない。

PARALLEL Runtimeは全workerの起動を先に完了してから回収を開始し、各workerおよびTest/Reviewの起動直前に承認raw-byte digestを再検証する。安全なartifact directory確定後の失敗は、実stageと専用reason codeを持つstatus／BLOCKED manifestとして固定する。

## テストコマンド

Pythonテストは各worktreeのルートで、共有仮想環境を使って実行する。

```powershell
C:\Users\sakag\other\ai_match_mvp\.venv\Scripts\python.exe -m pytest
```

Flutterテストは `flutter_app/` で実行する。

```powershell
flutter analyze
flutter test
```
