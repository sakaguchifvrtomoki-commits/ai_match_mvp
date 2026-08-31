# Task Brief

## Task ID

`<一意なID>`

## Human Goal

<達成したい結果>

## Current Baseline

<関連する現行仕様、実装、branch、既知のテスト状態>

- **Baseline commit SHA:** `<完全なcommit SHA>`
- **Referenced Specification:** `<参照する仕様書のパス>`
- **Target Sections:** <章、見出し、行など>

## Assumptions

- <明示できる前提。なければ「なし」>

## Human Decisions Required

- <判断事項、選択肢、影響、推奨案。なければ「なし」>

## Agent Plan

### Backend — RUN / SKIP

- **Goal:** <担当する成果。SKIPの場合は理由>
- **Worktree Absolute Path:** `C:\Users\sakag\other\fairies-backend`
- **Branch:** `agent/backend`
- **Start Commit SHA:** `<完全なcommit SHA>`
- **RUN Mode:** `READ ONLY / WRITE`
- **Allowed Files:** <変更可能なファイルまたは範囲>
- **Forbidden Files:** <変更禁止のファイルまたは範囲>
- **Acceptance Criteria:** <検証可能な完了条件>
- **Test Commands:** `<実行コマンド。なければ「なし」>`
- **Dependencies:** <先行条件や入力。なければ「なし」>
- **Handoff Format:** <commit SHA、変更概要、テスト結果、既知の問題など>

### Flutter — RUN / SKIP

- **Goal:**
- **Worktree Absolute Path:** `C:\Users\sakag\other\fairies-flutter`
- **Branch:** `agent/flutter`
- **Start Commit SHA:**
- **RUN Mode:** `READ ONLY / WRITE`
- **Allowed Files:**
- **Forbidden Files:**
- **Acceptance Criteria:**
- **Test Commands:**
- **Dependencies:**
- **Handoff Format:**

### Test/Review — RUN / SKIP

- **Goal:**
- **Worktree Absolute Path:** `C:\Users\sakag\other\fairies-test`
- **Branch:** `agent/test-review`
- **Start Commit SHA:**
- **RUN Mode:** `READ ONLY / WRITE`
- **Allowed Files:** <レビューのみの `READ ONLY` では「なし」>
- **Read Targets:** <レビューで参照するファイル。WRITEの場合は必要に応じて記載>
- **Forbidden Files:**
- **Acceptance Criteria:**
- **Test Commands:**
- **Dependencies:**
- **Handoff Format:**

### Integration — RUN / SKIP

- **Goal:**
- **Worktree Absolute Path:** `C:\Users\sakag\other\fairies-integration`
- **Branch:** `agent/integration`
- **Start Commit SHA:**
- **RUN Mode:** `READ ONLY / WRITE`
- **Allowed Files:**
- **Forbidden Files:**
- **Acceptance Criteria:**
- **Test Commands:**
- **Dependencies:**
- **Handoff Format:**

### Orchestrator — RUN / SKIP

- **Goal:** <追加の司令塔作業が必要な場合のみ記載。通常はSKIP>
- **Worktree Absolute Path:** `C:\Users\sakag\other\fairies-orchestrator`
- **Branch:** `agent/orchestrator`
- **Start Commit SHA:**
- **RUN Mode:** `READ ONLY / WRITE`
- **Allowed Files:**
- **Forbidden Files:** <production codeおよびmerge操作を含む>
- **Acceptance Criteria:**
- **Test Commands:**
- **Dependencies:**
- **Handoff Format:**

## File Ownership and Handoff

- **Overlap Check:** <Integrationの統合操作を除き、RUN Agent間でAllowed Filesが重複しないことを確認>
- **Sequential Exception:** <重複が必要な場合の先行Agent → 後続Agent。なければ「なし」>
- **Successor Start Condition:** <先行commit SHA。なければ「なし」>
- **Ownership Transfer Condition:** <引き渡すファイル、完了条件、引き渡し後の先行Agentの変更禁止。なければ「なし」>

## Integration Order

1. <commitまたは成果物の統合順。並列可能なものは明記>

## Human Verification

- <自動判定条件と分離した、統合後に人間が確認する価値、UX、実機動作、外部連携など>

## Issuance Gate

- [ ] Baseline commit SHA、参照する仕様書、対象セクションが記載されている。
- [ ] 各RUN AgentのWorktree absolute path、Branch、Start commit SHA、RUN modeが記載されている。
- [ ] 各RUN AgentのAcceptance Criteriaが検証可能であり、空欄、未確定、主観だけではない。
- [ ] 人間判断が必要な未確定事項はHuman Decisions Requiredへ戻されている。
- [ ] Integrationの統合操作を除き、RUN Agent間のAllowed Filesに未調整の重複がない。
- [ ] レビューのみのTest/ReviewはREAD ONLYで、Allowed Filesが「なし」である。
- [ ] UXの自動判定条件とHuman Verificationが分離されている。

すべてを満たすまでTask Briefを発行せず、Agentは着手しない。各RUN Agentは着手時にもworktree、branch、Start commit SHAを照合し、差異があれば着手せず報告する。
