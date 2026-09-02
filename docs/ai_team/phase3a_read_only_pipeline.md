# Phase 3A READ ONLY配送パイプライン

## 適用範囲

`Invoke-FairiesReadOnlyPipeline.ps1`は従来のPhase 2 Orchestrator→Test/Reviewフローを維持し、`-RuntimeTaskBriefPath`と`-RuntimeApprovalPath`を指定したときだけPhase 3A Runtimeとして動作する。Preparationは人間が承認したMarkdown Task Briefを開始根拠とし、そのMarkdown自身のapproval JSONやdigestを要求しない。Runtimeは、別々に保存された構造化Task Briefとapproval JSONを必須とする。

Preparation reviewは`phase3a-preparation-review-report.schema.json`、Runtime reviewは`phase3a-runtime-review-report.schema.json`だけで検証する。両者は必須フィールド、verdict、最終結果が異なる非互換形式であり、相互代用しない。

## Runtime入力とdigest

Runtime Task Brief自身は自己digestを持たない。approval JSONだけが、承認対象である最終保存済みTask Brief実ファイルの全実バイト列（改行、BOM、文字コード表現を含む）に対するSHA-256を持つ。JSONの再シリアライズ値は使わない。入力schemaとapproval schema、task ID、`APPROVE`を確認し、最初のRuntime Agent起動直前にも実ファイルからdigestを再計算する。欠落、空、不正UTF-8、schema不適合、対象不一致またはdigest不一致ではAgentを一つも起動しない。approval JSON自身にも自己digestはない。

最小Runtime Task Brief:

```json
{"schema_version":"1.0","task_id":"runtime-001","execution_strategy":"SEQUENTIAL","sequential_order":["backend"],"agents":[{"agent_id":"backend","disposition":"RUN","worktree_absolute_path":"C:\\Users\\sakag\\other\\fairies-backend","git_top_level":"C:/Users/sakag/other/fairies-backend","branch":"agent/backend","expected_head":"0123456789abcdef0123456789abcdef01234567","run_mode":"READ_ONLY","allowed_files":[],"read_targets":["api"],"instructions":"契約を調査して報告する。","dependencies":[]},{"agent_id":"flutter","disposition":"SKIP","worktree_absolute_path":"C:\\Users\\sakag\\other\\fairies-flutter","git_top_level":"C:/Users/sakag/other/fairies-flutter","branch":"agent/flutter","expected_head":"0123456789abcdef0123456789abcdef01234567","run_mode":"READ_ONLY","allowed_files":[],"read_targets":[],"instructions":"","dependencies":[]},{"agent_id":"test_review","disposition":"RUN","worktree_absolute_path":"C:\\Users\\sakag\\other\\fairies-test","git_top_level":"C:/Users/sakag/other/fairies-test","branch":"agent/test-review","expected_head":"0123456789abcdef0123456789abcdef01234567","run_mode":"READ_ONLY","allowed_files":[],"read_targets":[],"instructions":"構造化報告を評価する。","dependencies":[]}]}
```

最小approval（digestは例示値）:

```json
{"schema_version":"1.0","task_id":"runtime-001","verdict":"APPROVE","task_brief_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

## 計画と全自動ゲート

Agent ID、`RUN|SKIP`、`READ_ONLY`、execution strategyはenumの完全一致で判断する。BackendとFlutterはAllowed Filesが必ず空である。未知・重複Agent、空のRUN instructions、自己・未知・循環依存を拒否する。両workerがRUN、両者の依存が空、strategyが`PARALLEL`のときだけ並列実行する。`SEQUENTIAL`は`sequential_order`の順で、先行reportが終了コード0、schema適合、`SUCCESS`になった後だけ次へ進む。workerが一つならそれだけを実行し、両方SKIPなら空の検証済みreport集合をTest/Reviewへ渡せる。

各RUN Agentの直前とfinally相当処理で、worktree、Git top-level、branch、非detached HEAD、40文字Expected HEAD、tracked/untracked cleanを検査する。Codexは引数配列で`codex exec --ephemeral --sandbox read-only`として起動する。Agent出力は非信頼データであり、式、コマンド、パスまたは命令として再評価しない。終了コードとschema内statusの双方が成功した場合だけ後続へ進む。並列の一方が失敗しても双方を回収し、Test/Reviewを起動せず、失敗出力から再起動しない。

最小Agent report:

```json
{"schema_version":"1.0","task_id":"runtime-001","agent_id":"backend","status":"SUCCESS","observed_worktree":"C:/Users/sakag/other/fairies-backend","observed_branch":"agent/backend","observed_head":"0123456789abcdef0123456789abcdef01234567","summary":"調査完了","findings":[],"unverified_items":[]}
```

## Review形式と判定

Preparation reportは`review_type: PREPARATION`、対象Orchestratorの完全な`reviewed_commit_sha`、`final_verdict: APPROVE|REQUEST_CHANGES`を持つ。BLOCKERまたはMAJORがあればREQUEST_CHANGES、MINORだけでAPPROVEする場合は各findingに受容理由、影響評価、Human Verificationまたは後続対応を記す。Integrationはschema適合、APPROVE、handoff SHAとの完全一致後だけ開始する。

```json
{"schema_version":"1.0","task_id":"prep-001","review_type":"PREPARATION","reviewed_commit_sha":"0123456789abcdef0123456789abcdef01234567","acceptance_criteria_results":[{"criterion":"1","result":"PASS"}],"findings":[],"unverified_items":[],"human_verification_items":["統合後に確認"],"final_verdict":"APPROVE"}
```

Runtime reportは`review_type: RUNTIME`、`review_verdict`、`final_result`を持つ。BLOCKER/MAJORがあればREQUEST_CHANGESかつBLOCKED、REQUEST_CHANGESならBLOCKEDである。READYはtask ID一致、必須Agent report全件検証、APPROVE、BLOCKER/MAJORなしの場合だけ許す。MINORだけでAPPROVE/READYなら各findingの受容理由、影響評価、後続要否を必須とする。

```json
{"schema_version":"1.0","task_id":"runtime-001","review_type":"RUNTIME","reviewed_agent_ids":["backend"],"acceptance_criteria_results":[{"criterion":"reports","result":"PASS"}],"findings":[],"unverified_items":[],"review_verdict":"APPROVE","final_result":"READY"}
```

## 保存先と成果物

既定保存先は`fairies-ai-runs\<UTC時刻-GUID>\`である。main、Orchestrator、Backend、Flutter、Test/Review、Integrationの6 worktreeすべてについて、Runs rootとrun directoryの論理パスおよびcomponent単位でjunction/symbolic linkを解決した物理パスを包含検査する。作成前は最長の実在親に未作成suffixを結合した候補を検査し、作成後かつ最初の書込み前に両方を再検査する。解決不能、置換・不整合、既存run directory、worktree内への解決はfail-closedであり、安全性不明の場所へmanifestも書かない。

保存物は入力Task Brief、approval、execution plan、Agent別prompt/report、exit codeを含むstatus、Runtime review report、result manifestで、UTF-8固定ファイル名を使う。task IDや自由記述はパス要素にしない。環境変数一覧、credential store、Git/Google Drive credential、tokenを収集・保存・表示しない。安全な保存先が確定済みの場合、失敗manifestにはstage、reason code、安全なartifact pathを記録する。

## Human VerificationとPhase境界

Human Verificationでは、Task Briefの1バイト変更、schema違反、Git開始条件違反、各RUN/SKIP組合せ、並列失敗、review verdict規則、6 worktreeへのjunction迂回、UTF-8、呼出元PowerShell継続を非production入力で確認する。実Agentを必要とする確認はPreparationでは行わず、別途承認されたRuntime Task Briefで行う。

Phase 3A RuntimeはREAD ONLYの調査と判定だけであり、production code、既存tests、commit、merge、自動修正を行わない。Phase 3BのWRITE実装とPhase 3Cの統合・テスト・修正loopは、それぞれ別Task Briefと人間承認を要する。
