# Fairies Phase 1 AI開発チーム運用ルール

## 体制と担当

Phase 1では、4つのGit worktreeとbranchを使って並行作業する。各Agentは割り当てられたworktreeとbranchだけで作業する。

| Branch | 担当 |
| --- | --- |
| `agent/backend` | `api/`、Python backend、Python tests |
| `agent/flutter` | `flutter_app/`、Flutter tests |
| `agent/test-review` | レビューとテスト。production codeは原則変更しない |
| `agent/integration` | commit統合、競合対応、全テスト、統合後レビュー |

通常の開発ブランチは `feature/v0.2.2-fastapi` とし、上記の `agent/*` branchはPhase 1の正式な例外とする。

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
