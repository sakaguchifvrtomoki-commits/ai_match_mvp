# Phase 3B WRITE配送パイプライン

## 適用範囲

`Invoke-FairiesWritePipeline.ps1`は、人間承認済みの構造化WRITE Task Briefに基づくBackend／Flutterのworking tree編集と、Test/ReviewによるREAD ONLY審査を配送するPhase 3B専用entrypointである。Phase 3Aのentrypoint、schema、artifactおよび契約を参照・変更しない。Preparationでは実Agent Runtime E2Eを行わず、`Test-FairiesWritePipeline.ps1`の一時repositoryとfake processだけを使用する。

## 入力とschema

入力はWRITE Task BriefとHuman Approvalの2ファイルである。Task Briefは自己digestを持たず、Approvalが最終保存済みTask Briefのraw bytesに対するSHA-256を持つ。pipelineはschema、task ID、APPROVE、digestをpreflightと各Agent起動直前に再検証する。

Phase 3B専用schemaは次の6件である。

- `phase3b-write-task-brief.schema.json`: 実行戦略、Agent、Allowed／Forbidden Files、固定Test Commands。
- `phase3b-write-approval.schema.json`: 人間承認とraw-byte digest。
- `phase3b-implementation-report.schema.json`: WRITE Agentの主張。Git evidenceの正本にはしない。
- `phase3b-write-review-report.schema.json`: reviewed digest、finding、verdict、Phase 3C判定。
- `phase3b-agent-status.schema.json`: 起動・終了・validation stage・Git pre/postflight。
- `phase3b-result-manifest.schema.json`: safe artifact directory、Baseline、digest、最終結果。

すべてのschemaは`additionalProperties: false`、required、enumおよびdigest patternでfail-closedにする。schemaで表現しきれないAgent集合、RUN／SKIP、dependency、順序、path包含および物理衝突はpipelineが追加検証する。Test/Reviewは常にRUN／READ_ONLY／Allowed Files空である。RUNするWRITE AgentのAllowed Filesは空にできず、SKIP AgentのAllowed Files、Test Commandsおよびdependenciesは空である。

## Runtime制御

1. 入力raw bytes、schema、approval digest、task identity、Baselineおよびexecution planを検証する。
2. Allowed／Forbidden Filesをrepository-relative pathとして正規化し、absolute path、空要素、`.`、`..`、ADS、glob、case差の衝突、包含および物理path衝突を拒否する。Forbidden Filesを優先する。
3. artifact rootとrun directoryについて、作成前後に全既知worktreeおよびTask Briefのworktree外となる論理・物理pathを確認する。reparse pointをcomponent単位で解決できなければ書き込まない。
4. RUN Agentごとにphysical Git top-level、branch、non-detached HEAD、Expected HEAD、tracked／staged／untracked cleanを起動直前に確認する。
5. WRITE Agentを`workspace-write`、Test/Reviewを`read-only`で起動する。Agent出力は非信頼データとしてコマンド、pathまたは式に再評価しない。
6. SEQUENTIALは先行成功後だけ後続を起動する。PARALLELはBackend／Flutter双方RUN、依存なし、別worktree、同一Baseline、path非衝突のときだけ許し、片系失敗でも起動済みprocessをすべて回収する。
7. 親pipelineがBaselineからのtracked、untracked、delete、renameおよびstaged変更を収集する。Git index、HEAD、branchの変更、Allowed Files外、Forbidden Filesまたはscope escapeをBLOCKEDにする。
8. Task Briefに完全な構造化値として記載されたTest Commandsだけを実行する。`ProcessStartInfo.ArgumentList`へexecutableとargvを分けて渡し、shell文字列、`Invoke-Expression`、`ScriptBlock.Create`、`pwsh -Command`またはAgent出力による補完を使用しない。
9. 全workerとtest成功後だけTest/Reviewを起動し、reviewed artifact digestを親pipelineのdigestと照合する。
10. APPROVE、BLOCKER／MAJORなし、digest一致の場合だけ`READY_FOR_PHASE3C` manifestを作る。Phase 3B Runtime内ではstage、commit、merge、Integration起動を行わない。

PARALLEL実行はprocess startとcollectionを分離し、各start直前にapproval gateを再実行する。途中のstart失敗・digest変更・timeout・片系失敗でも開始済みprocessを全件回収する。SEQUENTIAL実行は先行processの成功を回収してから次を開始する。

## fail-closed制御

schema、approval、digest、Agent集合、dependency、順序、path、artifact destination、Git identityまたはclean stateの不一致ではAgentを起動しない。WRITE不能でも権限昇格しない。worker非ゼロ、timeout、report欠落・不正、staged変更、許可外差分、test失敗またはreview拒否ではTest/ReviewまたはPhase 3Cへ進めない。REQUEST_CHANGES後の自動修正loop、rollback、reset、clean、checkout、rebaseおよびbranch切替は行わない。安全なartifact directoryが確定済みの場合だけ、秘密情報を含めないreason code付きfailure evidenceを保存できる。

## artifactとPhase 3C handoff

artifact rootにはworktree外の明示pathを使用し、Task Brief／Approval原本、Agent report、Git evidence、差分／untracked artifact、test evidence、review reportおよびmanifestを保存する。自由記述やtask IDをpath要素へ使用せず、credential、token、環境変数一覧を収集しない。

authoritative schema 6件、各processの実argv・working directory・開始終了時刻・exit code・timeout・stdout/stderr、schema-valid Agent status、binary patch、content-addressed untracked bytes、change bundle、固定review入力、開始時／postflight Git evidenceおよび最終artifact inventoryを保存する。失敗manifestは実際のvalidation stageと専用reason codeを保持する。

Phase 3Cへ渡せるのはAPPROVE済みのimmutableな差分bundleまたはpatch、Baseline SHA、各SHA-256、staged files 0件のevidence、test evidence、review reportおよびmanifestだけである。Phase 3Cは同一digestを再検証してからcommitする。

## 専用test harness

固定Test Commandは次の1件だけである。

```text
executable: pwsh
argv: -NoProfile, -NonInteractive, -File, scripts/ai_team/Test-FairiesWritePipeline.ps1
working directory: repository root
timeout: 600 seconds
```

harnessはPowerShell Parser、JSON parse、`Test-Json`のpositive／negative fixture、digest、dirty／staged Git、tracked／untracked／delete／rename、Allowed Files、path escape、worker失敗、timeout、parallel片系失敗およびreview fail-closedを検証する。一時fixtureはOS temp配下の固有directoryに作り、安全性を再確認して後始末する。production Codex、実Agent、network、外部サービス、Android、Google Driveおよび本番環境は使用しない。
