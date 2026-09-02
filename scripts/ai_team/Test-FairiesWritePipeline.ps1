#requires -Version 7.0
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$pipeline = Join-Path $PSScriptRoot 'Invoke-FairiesWritePipeline.ps1'
$schemaRoot = Join-Path $root 'docs\ai_team\schemas'
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('fairies-phase3b-test-' + [Guid]::NewGuid().ToString('N'))
$passed = [Collections.Generic.List[string]]::new()

function Assert-True([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Assert-Throws([scriptblock]$Action, [string]$Pattern, [string]$Name) {
    try { & $Action; throw "Expected rejection was not raised: $Name" }
    catch { if ($_.Exception.Message -like "Expected rejection was not raised:*") { throw }; if ($_.Exception.Message -notmatch $Pattern) { throw "Unexpected rejection for $Name`: $($_.Exception.Message)" } }
    $passed.Add($Name)
}
function Invoke-TestGit([string]$Repo, [string[]]$Arguments) {
    $result = Invoke-F3BProcess git (@('-C',$Repo) + $Arguments) $Repo 30
    if ($result.ExitCode -ne 0) { throw "Fixture Git failure: $($result.Stderr)" }
    $result.Stdout.Trim()
}
function Write-TestFile([string]$Path, [string]$Text) {
    $parent = Split-Path $Path -Parent
    if (-not [IO.Directory]::Exists($parent)) { [void][IO.Directory]::CreateDirectory($parent) }
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

[void][IO.Directory]::CreateDirectory($temporaryRoot)
try {
    . $pipeline -LibraryOnly

    foreach ($powerShellFile in @($pipeline, $PSCommandPath)) {
        $tokens = $null; $errors = $null
        [void][Management.Automation.Language.Parser]::ParseFile($powerShellFile, [ref]$tokens, [ref]$errors)
        Assert-True ($errors.Count -eq 0) "PowerShell syntax error in $powerShellFile`: $($errors | Out-String)"
    }
    $passed.Add('PowerShell parser')

    $schemaNames = @(
        'phase3b-write-task-brief.schema.json', 'phase3b-write-approval.schema.json',
        'phase3b-implementation-report.schema.json', 'phase3b-write-review-report.schema.json',
        'phase3b-agent-status.schema.json', 'phase3b-result-manifest.schema.json'
    )
    foreach ($name in $schemaNames) {
        $text = [IO.File]::ReadAllText((Join-Path $schemaRoot $name), [Text.UTF8Encoding]::new($false, $true))
        $schemaObject = $text | ConvertFrom-Json -Depth 50 -ErrorAction Stop
        Assert-True ($schemaObject.additionalProperties -eq $false) "$name is not fail-closed"
    }
    $passed.Add('JSON schema parsing')

    $sha = '1' * 40
    $task = [ordered]@{
        schema_version='1.0'; task_id='fixture'; baseline_sha=$sha; execution_strategy='SEQUENTIAL'; sequential_order=@('backend')
        agents=@(
            [ordered]@{agent_id='backend';disposition='RUN';worktree_absolute_path='C:\fixture\backend';git_top_level='C:\fixture\backend';branch='agent/backend';expected_head=$sha;run_mode='WRITE';allowed_files=@('api');forbidden_files=@('api/secret');instructions='edit';test_commands=@();dependencies=@()},
            [ordered]@{agent_id='flutter';disposition='SKIP';worktree_absolute_path='C:\fixture\flutter';git_top_level='C:\fixture\flutter';branch='agent/flutter';expected_head=$sha;run_mode='WRITE';allowed_files=@();forbidden_files=@();instructions='';test_commands=@();dependencies=@()},
            [ordered]@{agent_id='test_review';disposition='RUN';worktree_absolute_path='C:\fixture\test';git_top_level='C:\fixture\test';branch='agent/test-review';expected_head=$sha;run_mode='READ_ONLY';allowed_files=@();forbidden_files=@();instructions='review';test_commands=@();dependencies=@()}
        )
    }
    $taskJson = $task | ConvertTo-Json -Depth 30
    Assert-True ($taskJson | Test-Json -SchemaFile (Join-Path $schemaRoot 'phase3b-write-task-brief.schema.json')) 'Positive Task Brief fixture failed schema validation'
    $badTask = $taskJson | ConvertFrom-Json -Depth 30; $badTask.agents[0].allowed_files = @('../escape')
    Assert-True (-not (($badTask | ConvertTo-Json -Depth 30) | Test-Json -SchemaFile (Join-Path $schemaRoot 'phase3b-write-task-brief.schema.json') -ErrorAction SilentlyContinue)) 'Path escape fixture was schema-valid'
    $badReview = '{"schema_version":"1.0","task_id":"fixture","review_type":"WRITE_RUNTIME","reviewed_agent_ids":["backend"],"reviewed_artifact_sha256":"' + ('a'*64) + '","acceptance_criteria_results":[{"criterion":"1","result":"PASS"}],"findings":[{"severity":"MAJOR","location":"x","reproduction_condition":"x","expected_result":"x"}],"unverified_items":[],"review_verdict":"APPROVE","final_result":"READY_FOR_PHASE3C"}'
    Assert-True (-not ($badReview | Test-Json -SchemaFile (Join-Path $schemaRoot 'phase3b-write-review-report.schema.json') -ErrorAction SilentlyContinue)) 'MAJOR finding allowed READY'
    $passed.Add('Schema positive and negative fixtures')

    Assert-Throws { Assert-F3BRelativePath '..\escape' } 'INVALID_RELATIVE_PATH' 'parent path escape'
    Assert-Throws { Assert-F3BRelativePath 'C:\absolute' } 'INVALID_RELATIVE_PATH' 'absolute path'
    Assert-Throws { Assert-F3BRelativePath 'api/file.txt:stream' } 'INVALID_RELATIVE_PATH' 'ADS path'
    Assert-Throws { Assert-F3BRelativePath 'api/*.py' } 'INVALID_RELATIVE_PATH' 'glob path'
    Assert-True (Test-F3BPathPolicy 'api/good.py' @('api') @('api/secret')) 'Allowed path rejected'
    Assert-True (-not (Test-F3BPathPolicy 'api/secret/key.txt' @('api') @('api/secret'))) 'Forbidden path did not override allowed path'
    $passed.Add('Path policy')

    $collision = $taskJson | ConvertFrom-Json -Depth 30
    $collision.agents[1].disposition='RUN'; $collision.agents[1].allowed_files=@('API/models'); $collision.agents[1].instructions='edit'; $collision.sequential_order=@('backend','flutter'); $collision.agents[1].worktree_absolute_path=$collision.agents[0].worktree_absolute_path
    Assert-Throws { Assert-F3BPlan $collision } 'ALLOWED_PATH_COLLISION|PARALLEL|WRITE_AGENT' 'allowed path containment collision'

    $repo = Join-Path $temporaryRoot 'repo'
    [void][IO.Directory]::CreateDirectory($repo)
    [void](Invoke-TestGit $repo @('init','--initial-branch=agent/backend'))
    [void](Invoke-TestGit $repo @('config','user.name','Phase3B Fixture'))
    [void](Invoke-TestGit $repo @('config','user.email','fixture@example.invalid'))
    Write-TestFile (Join-Path $repo 'allowed/base.txt') 'base'
    Write-TestFile (Join-Path $repo 'rename-me.txt') 'rename'
    [void](Invoke-TestGit $repo @('add','allowed/base.txt','rename-me.txt'))
    [void](Invoke-TestGit $repo @('commit','-m','fixture'))
    $head = Invoke-TestGit $repo @('rev-parse','HEAD')
    $agent = [pscustomobject]@{agent_id='backend';worktree_absolute_path=$repo;git_top_level=$repo;branch='agent/backend';expected_head=$head;allowed_files=@('allowed','rename-me.txt');forbidden_files=@('allowed/forbidden')}
    [void](Get-F3BGitState $agent -RequireClean)
    Write-TestFile (Join-Path $repo 'allowed/untracked.txt') 'new'
    Write-TestFile (Join-Path $repo 'allowed/base.txt') 'changed'
    $changes = @(Get-F3BChangedFiles $agent)
    Assert-True ('allowed/untracked.txt' -cin $changes -and 'allowed/base.txt' -cin $changes) "Tracked or untracked change was not detected. Actual: $($changes -join ', ')"
    $passed.Add('tracked and untracked detection')
    [IO.File]::Delete((Join-Path $repo 'allowed/base.txt'))
    $changes = @(Get-F3BChangedFiles $agent)
    Assert-True ('allowed/base.txt' -cin $changes) 'Delete was not detected'
    $passed.Add('delete detection')
    [void](Invoke-TestGit $repo @('restore','allowed/base.txt'))
    [IO.File]::Move((Join-Path $repo 'rename-me.txt'), (Join-Path $repo 'allowed/renamed.txt'))
    $changes = @(Get-F3BChangedFiles $agent)
    Assert-True ('rename-me.txt' -cin $changes -and 'allowed/renamed.txt' -cin $changes) 'Rename endpoints were not detected'
    $passed.Add('rename detection')
    Write-TestFile (Join-Path $repo 'outside.txt') 'bad'
    Assert-Throws { [void](Get-F3BChangedFiles $agent) } 'CHANGE_OUTSIDE_ALLOWLIST' 'outside allowlist change'
    [void](Invoke-TestGit $repo @('add','allowed/renamed.txt'))
    Assert-Throws { [void](Get-F3BChangedFiles $agent) } 'STAGED_CHANGE' 'staged change'
    Assert-Throws { [void](Get-F3BGitState $agent -RequireClean) } 'DIRTY_WORKTREE' 'dirty worktree'

    [void](Invoke-TestGit $repo @('restore','--staged','allowed/renamed.txt'))
    [IO.File]::Delete((Join-Path $repo 'outside.txt'))
    $measured=@(Get-F3BChangedFiles $agent)
    $state=Get-F3BGitState $agent
    $goodReport=[pscustomobject]@{task_id='fixture';agent_id='backend';status='SUCCESS';observed_worktree=$repo;observed_branch='agent/backend';observed_head=$head;claimed_changed_files=$measured}
    Assert-F3BImplementationReport $goodReport $agent 'fixture' $measured $state $state
    $passed.Add('implementation report and Git agreement')
    $blocked=$goodReport.PSObject.Copy();$blocked.status='BLOCKED'
    Assert-Throws { Assert-F3BImplementationReport $blocked $agent 'fixture' $measured $state $state } 'REPORT_IDENTITY_OR_STATUS_MISMATCH' 'implementation BLOCKED rejection'
    $missing=$goodReport.PSObject.Copy();$missing.claimed_changed_files=@()
    Assert-Throws { Assert-F3BImplementationReport $missing $agent 'fixture' $measured $state $state } 'REPORT_FILE_SET_MISMATCH' 'implementation file mismatch'

    $bundleDir=Join-Path $temporaryRoot 'bundle';[void][IO.Directory]::CreateDirectory($bundleDir)
    $bundle=New-F3BChangeBundle $agent $measured $bundleDir
    Assert-True ([IO.File]::Exists((Join-Path $bundleDir 'backend-tracked.patch'))) 'Tracked binary patch missing'
    Assert-True (@($bundle.metadata.untracked).Count -gt 0) 'Untracked content metadata missing'
    foreach($entry in @($bundle.metadata.untracked)){Assert-True ((Get-F3BFileSha256 (Join-Path $bundleDir $entry.artifact)) -ceq $entry.sha256) 'Untracked content digest mismatch'}
    $passed.Add('restorable patch and content-addressed untracked bytes')

    $statusBrief=[pscustomobject]@{task_id='fixture'};$statusAgent=[pscustomobject]@{agent_id='backend';disposition='RUN'}
    $status=New-F3BAgentStatus $statusBrief $statusAgent;Write-F3BAgentStatus $bundleDir $status
    Assert-True ((Read-F3BUtf8 (Join-Path $bundleDir 'backend-status.json')) | Test-Json -SchemaFile (Join-Path $schemaRoot 'phase3b-agent-status.schema.json')) 'Agent status producer output invalid'
    $passed.Add('agent status producer and schema')

    $briefPath = Join-Path $temporaryRoot 'brief.json'; Write-TestFile $briefPath $taskJson
    $digest = Get-F3BFileSha256 $briefPath
    $approvalPath = Join-Path $temporaryRoot 'approval.json'
    Write-TestFile $approvalPath (([ordered]@{schema_version='1.0';task_id='fixture';verdict='APPROVE';task_brief_sha256=$digest} | ConvertTo-Json -Compress))
    $approval = Read-F3BSchemaJson $approvalPath 'phase3b-write-approval.schema.json'
    Assert-True ($approval.task_brief_sha256 -ceq $digest) 'Valid digest was rejected'
    Write-TestFile $briefPath ($taskJson + ' ')
    Assert-True ((Get-F3BFileSha256 $briefPath) -cne $approval.task_brief_sha256) 'Raw-byte digest mismatch was not observable'
    $passed.Add('raw-byte approval digest')

    $stub = Join-Path $temporaryRoot 'stub.ps1'
    Write-TestFile $stub "param([int]`$Code=0,[int]`$Delay=0); if(`$Delay){Start-Sleep -Seconds `$Delay}; exit `$Code"
    $ok = Invoke-F3BProcess pwsh @('-NoProfile','-NonInteractive','-File',$stub,'-Code','0') $temporaryRoot 10
    Assert-True ($ok.ExitCode -eq 0) 'Fake process success failed'
    $failed = Invoke-F3BProcess pwsh @('-NoProfile','-NonInteractive','-File',$stub,'-Code','7') $temporaryRoot 10
    Assert-True ($failed.ExitCode -eq 7) 'Fake process failure was not collected'
    Assert-Throws { [void](Invoke-F3BProcess pwsh @('-NoProfile','-NonInteractive','-File',$stub,'-Delay','2') $temporaryRoot 1) } 'PROCESS_TIMEOUT' 'fake worker timeout'
    Assert-True ($failed.ExitCode -ne 0 -and $ok.ExitCode -eq 0) 'Parallel partial failure evidence was not retained'
    $passed.Add('fake-only worker failure and parallel collection')

    $pipelineText = [IO.File]::ReadAllText($pipeline)
    Assert-True ($pipelineText -notmatch 'Invoke-Expression|ScriptBlock[.]Create|pwsh\s+-Command') 'Dynamic command construction found'
    Assert-True ($pipelineText -notmatch 'Invoke-FairiesReadOnlyPipeline|phase3a-') 'Phase 3A coupling found'
    Assert-True ($pipelineText -match 'TASK_BRIEF_OR_APPROVAL_CHANGED') 'Per-Agent digest gate missing'
    Assert-True ($pipelineText -match 'TEST_WORKING_DIRECTORY_ESCAPE') 'Test working-directory physical gate missing'
    Assert-True ($pipelineText -match 'final_result=.BLOCKED') 'BLOCKED manifest producer missing'
    $passed.Add('No eval and Phase 3A isolation')

    "Phase 3B dedicated harness passed $($passed.Count) checks:"
    $passed | ForEach-Object { "PASS: $_" }
}
finally {
    if ([IO.Directory]::Exists($temporaryRoot)) {
        $resolved = [IO.Path]::GetFullPath($temporaryRoot)
        $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if (-not $resolved.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase) -or -not ([IO.Path]::GetFileName($resolved).StartsWith('fairies-phase3b-test-', [StringComparison]::Ordinal))) { throw "Unsafe fixture cleanup target: $resolved" }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
