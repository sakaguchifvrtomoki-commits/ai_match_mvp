#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$TaskBriefPath,
    [string]$ApprovalPath,
    [string]$RunsRoot = 'C:\Users\sakag\other\fairies-ai-runs',
    [string]$CodexExecutable = 'codex.cmd',
    [string[]]$CodexPrefixArgument = @(),
    [ValidateRange(1,3600)][int]$AgentTimeoutSeconds = 600,
    [switch]$LibraryOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Utf8 = [Text.UTF8Encoding]::new($false, $true)
$script:SchemaRoot = Join-Path (Split-Path $PSScriptRoot -Parent) '..\docs\ai_team\schemas'
$script:KnownWorktrees = @(
    'C:\Users\sakag\other\ai_match_mvp',
    'C:\Users\sakag\other\fairies-orchestrator',
    'C:\Users\sakag\other\fairies-backend',
    'C:\Users\sakag\other\fairies-flutter',
    'C:\Users\sakag\other\fairies-test',
    'C:\Users\sakag\other\fairies-integration'
)

function Get-F3BFullPath([string]$Path) {
    [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
}

function Test-F3BInside([string]$Candidate, [string]$Container) {
    $candidatePath = Get-F3BFullPath $Candidate
    $containerPath = Get-F3BFullPath $Container
    $candidatePath.Equals($containerPath, [StringComparison]::OrdinalIgnoreCase) -or
        $candidatePath.StartsWith($containerPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}

function Get-F3BPhysicalPath([string]$Path) {
    $full = Get-F3BFullPath $Path
    $root = [IO.Path]::GetPathRoot($full)
    $current = $root
    foreach ($part in [IO.Path]::GetRelativePath($root, $full).Split([IO.Path]::DirectorySeparatorChar, [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = [IO.Path]::Combine($current, $part)
        if (-not ([IO.File]::Exists($current) -or [IO.Directory]::Exists($current))) { continue }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            $target = $item.ResolveLinkTarget($true)
            if ($null -eq $target) { throw "PATH_REPARSE_UNRESOLVED: $current" }
            $current = Get-F3BPhysicalPath $target.FullName
        }
    }
    Get-F3BFullPath $current
}

function Assert-F3BSafeArtifactPath([string]$Path, [string[]]$Worktrees = $script:KnownWorktrees) {
    $logical = Get-F3BFullPath $Path
    $physical = Get-F3BPhysicalPath $logical
    foreach ($worktree in $Worktrees) {
        if (-not [IO.Directory]::Exists($worktree)) { continue }
        if ((Test-F3BInside $logical (Get-F3BFullPath $worktree)) -or (Test-F3BInside $physical (Get-F3BPhysicalPath $worktree))) {
            throw "UNSAFE_ARTIFACT_PATH: $Path"
        }
    }
    $physical
}

function Read-F3BUtf8([string]$Path) {
    if (-not [IO.File]::Exists($Path)) { throw "FILE_MISSING: $Path" }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or $item.Length -eq 0 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "FILE_UNSAFE: $Path" }
    [IO.File]::ReadAllText($item.FullName, $script:Utf8)
}

function Read-F3BSchemaJson([string]$Path, [string]$SchemaName) {
    $text = Read-F3BUtf8 $Path
    $schema = Join-Path $script:SchemaRoot $SchemaName
    if (-not ($text | Test-Json -SchemaFile $schema -ErrorAction Stop)) { throw "SCHEMA_INVALID: $Path" }
    $text | ConvertFrom-Json -Depth 40 -ErrorAction Stop
}

function Get-F3BSha256Bytes([byte[]]$Bytes) {
    [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}

function Get-F3BFileSha256([string]$Path) { Get-F3BSha256Bytes ([IO.File]::ReadAllBytes($Path)) }

function Assert-F3BRelativePath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or [IO.Path]::IsPathFullyQualified($Path) -or
        $Path -match '(^|[\\/])\.{1,2}([\\/]|$)' -or $Path -match '[:*?"<>|]' -or
        $Path -match '(^|[\\/])([\\/]|$)' -or $Path.EndsWith('/') -or $Path.EndsWith('\')) {
        throw "INVALID_RELATIVE_PATH: $Path"
    }
}

function Test-F3BPathPolicy([string]$Path, [string[]]$Allowed, [string[]]$Forbidden) {
    Assert-F3BRelativePath $Path
    $normalized = $Path.Replace('\', '/').Trim('/')
    foreach ($rule in $Forbidden) {
        $r = $rule.Replace('\', '/').Trim('/')
        if ($normalized.Equals($r, [StringComparison]::OrdinalIgnoreCase) -or $normalized.StartsWith($r + '/', [StringComparison]::OrdinalIgnoreCase)) { return $false }
    }
    foreach ($rule in $Allowed) {
        $r = $rule.Replace('\', '/').Trim('/')
        if ($normalized.Equals($r, [StringComparison]::OrdinalIgnoreCase) -or $normalized.StartsWith($r + '/', [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    $false
}

function Assert-F3BPathSet([object[]]$Agents) {
    $claims = [Collections.Generic.List[object]]::new()
    foreach ($agent in $Agents | Where-Object disposition -CEQ RUN) {
        foreach ($path in @($agent.allowed_files)) {
            Assert-F3BRelativePath $path
            $logical = $path.Replace('\', '/').Trim('/')
            $physical = Get-F3BPhysicalPath (Join-Path $agent.worktree_absolute_path $path)
            if (Test-F3BInside $physical (Join-Path $agent.worktree_absolute_path '.git')) { throw 'GIT_METADATA_FORBIDDEN' }
            foreach ($claim in $claims) {
                $sameRepo = (Get-F3BFullPath $claim.Worktree).Equals((Get-F3BFullPath $agent.worktree_absolute_path), [StringComparison]::OrdinalIgnoreCase)
                $contains = $logical.Equals($claim.Logical, [StringComparison]::OrdinalIgnoreCase) -or $logical.StartsWith($claim.Logical + '/', [StringComparison]::OrdinalIgnoreCase) -or $claim.Logical.StartsWith($logical + '/', [StringComparison]::OrdinalIgnoreCase)
                $physicalCollision = $physical.Equals($claim.Physical, [StringComparison]::OrdinalIgnoreCase) -or (Test-F3BInside $physical $claim.Physical) -or (Test-F3BInside $claim.Physical $physical)
                if (($sameRepo -and $contains) -or $physicalCollision) { throw "ALLOWED_PATH_COLLISION: $logical" }
            }
            $claims.Add([pscustomobject]@{ Worktree = $agent.worktree_absolute_path; Logical = $logical; Physical = $physical })
        }
    }
}

function Assert-F3BPlan($Brief) {
    $ids = @($Brief.agents | ForEach-Object agent_id)
    if ($ids.Count -ne 3 -or ($ids | Sort-Object -Unique).Count -ne 3 -or @($ids | Where-Object { $_ -cnotin @('backend','flutter','test_review') }).Count) { throw 'AGENT_SET_INVALID' }
    $review = $Brief.agents | Where-Object agent_id -CEQ test_review
    if ($review.disposition -cne 'RUN' -or $review.run_mode -cne 'READ_ONLY' -or @($review.allowed_files).Count -or @($review.test_commands).Count -or @($review.dependencies).Count) { throw 'REVIEW_AGENT_INVALID' }
    $workers = @($Brief.agents | Where-Object agent_id -in @('backend','flutter'))
    foreach ($agent in $workers) {
        if ($agent.disposition -ceq 'RUN') {
            if ($agent.run_mode -cne 'WRITE' -or @($agent.allowed_files).Count -eq 0 -or [string]::IsNullOrWhiteSpace($agent.instructions)) { throw "WRITE_AGENT_INVALID: $($agent.agent_id)" }
        } elseif (@($agent.allowed_files).Count -or @($agent.test_commands).Count -or @($agent.dependencies).Count) { throw "SKIP_AGENT_INVALID: $($agent.agent_id)" }
        foreach ($path in @($agent.allowed_files) + @($agent.forbidden_files)) { Assert-F3BRelativePath $path }
        foreach ($dependency in @($agent.dependencies)) {
            if ($dependency -ceq $agent.agent_id) { throw 'SELF_DEPENDENCY' }
            $target = $workers | Where-Object agent_id -CEQ $dependency
            if ($null -eq $target -or $target.disposition -cne 'RUN') { throw 'UNKNOWN_OR_SKIP_DEPENDENCY' }
        }
    }
    $run = @($workers | Where-Object disposition -CEQ RUN)
    if ($Brief.execution_strategy -ceq 'PARALLEL') {
        if ($run.Count -ne 2 -or @($run | Where-Object { @($_.dependencies).Count }).Count -or
            (Get-F3BFullPath $run[0].worktree_absolute_path).Equals((Get-F3BFullPath $run[1].worktree_absolute_path), [StringComparison]::OrdinalIgnoreCase) -or $run[0].expected_head -cne $run[1].expected_head) { throw 'PARALLEL_PLAN_INVALID' }
        if (@($Brief.sequential_order).Count) { throw 'PARALLEL_ORDER_INVALID' }
    } elseif ($Brief.execution_strategy -ceq 'SEQUENTIAL') {
        if (@($Brief.sequential_order).Count -ne $run.Count -or @($Brief.sequential_order | Sort-Object -Unique).Count -ne $run.Count) { throw 'SEQUENTIAL_ORDER_INVALID' }
        foreach ($id in $Brief.sequential_order) { if ($id -cnotin @($run.agent_id)) { throw 'SEQUENTIAL_ORDER_INVALID' } }
        foreach ($agent in $run) { foreach ($dependency in @($agent.dependencies)) { if ([array]::IndexOf([object[]]@($Brief.sequential_order), $dependency) -ge [array]::IndexOf([object[]]@($Brief.sequential_order), $agent.agent_id)) { throw 'DEPENDENCY_ORDER_INVALID' } } }
    } else { throw 'STRATEGY_INVALID' }
    Assert-F3BPathSet $run
}

function Start-F3BProcess([string]$FileName, [string[]]$Arguments, [string]$WorkingDirectory, [string]$InputText = '') {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $FileName; $info.WorkingDirectory = $WorkingDirectory; $info.UseShellExecute = $false
    $info.RedirectStandardInput = $true; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { [void]$info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $info
    $started = [DateTime]::UtcNow
    try {
        if (-not $process.Start()) { throw 'PROCESS_START_FAILED' }
        $process.StandardInput.Write($InputText); $process.StandardInput.Close()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync(); $stderrTask = $process.StandardError.ReadToEndAsync()
        [pscustomobject]@{ Process=$process; StdoutTask=$stdoutTask; StderrTask=$stderrTask; StartedUtc=$started; FileName=$FileName; Arguments=@($Arguments); WorkingDirectory=$WorkingDirectory }
    } catch { $process.Dispose(); throw "PROCESS_START_FAILED: $($_.Exception.Message)" }
}

function Complete-F3BProcess($Handle, [int]$TimeoutSeconds) {
    $timedOut = -not $Handle.Process.WaitForExit($TimeoutSeconds * 1000)
    if ($timedOut) { try { $Handle.Process.Kill($true) } catch {}; $Handle.Process.WaitForExit() }
    $ended = [DateTime]::UtcNow
    try {
        [pscustomobject]@{ ExitCode=$(if($timedOut){$null}else{$Handle.Process.ExitCode}); Stdout=$Handle.StdoutTask.GetAwaiter().GetResult(); Stderr=$Handle.StderrTask.GetAwaiter().GetResult(); TimedOut=$timedOut; StartedUtc=$Handle.StartedUtc; EndedUtc=$ended; Collected=$true; FileName=$Handle.FileName; Arguments=@($Handle.Arguments); WorkingDirectory=$Handle.WorkingDirectory }
    } finally { $Handle.Process.Dispose() }
}

function Invoke-F3BProcess([string]$FileName, [string[]]$Arguments, [string]$WorkingDirectory, [int]$TimeoutSeconds, [string]$InputText = '') {
    Complete-F3BProcess (Start-F3BProcess $FileName $Arguments $WorkingDirectory $InputText) $TimeoutSeconds
}

function Invoke-F3BGit([string]$Worktree, [string[]]$Arguments, [switch]$AllowFailure) {
    $result = Invoke-F3BProcess git (@('-C', $Worktree) + $Arguments) $Worktree 30
    if (-not $AllowFailure -and $result.ExitCode -ne 0) { throw "GIT_FAILED: $($result.Stderr)" }
    $result
}

function Invoke-F3BGitNullList([string]$Worktree, [string[]]$Arguments) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = 'git'; $info.WorkingDirectory = $Worktree; $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    foreach ($argument in @('-C', $Worktree) + $Arguments) { [void]$info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $info
    $memory = [IO.MemoryStream]::new()
    try {
        if (-not $process.Start()) { throw 'GIT_START_FAILED' }
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.StandardOutput.BaseStream.CopyTo($memory)
        $process.WaitForExit()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw "GIT_FAILED: $stderr" }
        $items = [Collections.Generic.List[string]]::new(); $start = 0; $bytes = $memory.ToArray()
        for ($index = 0; $index -lt $bytes.Length; $index++) {
            if ($bytes[$index] -ne 0) { continue }
            if ($index -gt $start) { $items.Add($script:Utf8.GetString($bytes, $start, $index - $start)) }
            $start = $index + 1
        }
        if ($start -ne $bytes.Length) { throw 'GIT_NUL_OUTPUT_UNTERMINATED' }
        @($items)
    } finally { $memory.Dispose(); $process.Dispose() }
}

function Get-F3BGitState($Agent, [switch]$RequireClean) {
    if (-not [IO.Directory]::Exists($Agent.worktree_absolute_path)) { throw 'WORKTREE_MISSING' }
    $top = (Invoke-F3BGit $Agent.worktree_absolute_path @('rev-parse','--show-toplevel')).Stdout.Trim()
    $branch = (Invoke-F3BGit $Agent.worktree_absolute_path @('symbolic-ref','--quiet','--short','HEAD')).Stdout.Trim()
    $head = (Invoke-F3BGit $Agent.worktree_absolute_path @('rev-parse','--verify','HEAD')).Stdout.Trim()
    $status = (Invoke-F3BGit $Agent.worktree_absolute_path @('status','--porcelain=v1','--untracked-files=all')).Stdout
    if (-not (Get-F3BFullPath $top).Equals((Get-F3BFullPath $Agent.git_top_level), [StringComparison]::OrdinalIgnoreCase) -or
        -not (Get-F3BPhysicalPath $top).Equals((Get-F3BPhysicalPath $Agent.git_top_level), [StringComparison]::OrdinalIgnoreCase) -or
        -not (Get-F3BPhysicalPath $top).Equals((Get-F3BPhysicalPath $Agent.worktree_absolute_path), [StringComparison]::OrdinalIgnoreCase) -or
        $branch -cne $Agent.branch -or $head -cne $Agent.expected_head) { throw "GIT_IDENTITY_MISMATCH: $($Agent.agent_id)" }
    if ($RequireClean -and $status.Length) { throw "DIRTY_WORKTREE: $($Agent.agent_id)" }
    [pscustomobject]@{ top_level = $top; branch = $branch; head = $head; status = $status }
}

function Get-F3BChangedFiles($Agent) {
    $staged = @(Invoke-F3BGitNullList $Agent.worktree_absolute_path @('diff','--cached','--name-only','-z',$Agent.expected_head))
    if ($staged.Count) { throw "STAGED_CHANGE: $($Agent.agent_id)" }
    $tracked = @(Invoke-F3BGitNullList $Agent.worktree_absolute_path @('diff','--name-only','-z',$Agent.expected_head))
    $untracked = @(Invoke-F3BGitNullList $Agent.worktree_absolute_path @('ls-files','--others','--exclude-standard','-z'))
    $files = @($tracked + $untracked | Sort-Object -Unique)
    foreach ($file in $files) {
        if (-not (Test-F3BPathPolicy $file @($Agent.allowed_files) @($Agent.forbidden_files))) { throw "CHANGE_OUTSIDE_ALLOWLIST: $file" }
        $full = Join-Path $Agent.worktree_absolute_path $file
        if ([IO.File]::Exists($full) -or [IO.Directory]::Exists($full)) {
            $physical = Get-F3BPhysicalPath $full
            if (-not (Test-F3BInside $physical (Get-F3BPhysicalPath $Agent.worktree_absolute_path))) { throw "PATH_ESCAPE: $file" }
        }
    }
    $files
}

function Assert-F3BImplementationReport($Report, $Agent, [string]$TaskId, [string[]]$MeasuredFiles, $PreState, $PostState, [object[]]$TestEvidence) {
    if ($Report.task_id -cne $TaskId -or $Report.agent_id -cne $Agent.agent_id -or $Report.status -cne 'SUCCESS') { throw 'REPORT_IDENTITY_OR_STATUS_MISMATCH' }
    if (-not (Get-F3BPhysicalPath $Report.observed_worktree).Equals((Get-F3BPhysicalPath $Agent.worktree_absolute_path), [StringComparison]::OrdinalIgnoreCase) -or
        -not (Get-F3BPhysicalPath $Report.observed_git_top_level).Equals((Get-F3BPhysicalPath $PostState.top_level), [StringComparison]::OrdinalIgnoreCase) -or
        $Report.observed_branch -cne $PostState.branch -or $Report.pre_head -cne $PreState.head -or $Report.post_head -cne $PostState.head -or
        $PreState.head -cne $PostState.head) { throw 'REPORT_GIT_MISMATCH' }
    if (@($Report.staged_files).Count) { throw 'REPORT_STAGED_STATE_MISMATCH' }
    $claimed = @($Report.claimed_changed_files)
    foreach ($path in $claimed) { Assert-F3BRelativePath $path }
    if (@($claimed | Sort-Object -Unique).Count -ne $claimed.Count) { throw 'REPORT_DUPLICATE_FILE' }
    [array]$expected = @($MeasuredFiles | Sort-Object)
    [array]$actual = @($claimed | Sort-Object)
    if ($expected.Count -ne $actual.Count) { throw 'REPORT_FILE_SET_MISMATCH' }
    for ($i = 0; $i -lt $expected.Count; $i++) {
        if ($expected[$i] -cne $actual[$i]) { throw 'REPORT_FILE_SET_MISMATCH' }
    }
    $claims=@($Report.test_claims); $evidence=@($TestEvidence | Where-Object agent_id -CEQ $Agent.agent_id)
    if($claims.Count -ne $evidence.Count){throw 'REPORT_TEST_CLAIM_MISMATCH'}
    foreach($claim in $claims){$match=@($evidence|Where-Object command_id -CEQ $claim.command_id);if($match.Count-ne 1 -or $claim.exit_code-ne $match[0].exit_code -or [bool]$claim.timed_out-ne [bool]$match[0].timed_out){throw 'REPORT_TEST_CLAIM_MISMATCH'}}
}

function Write-F3BBytesArtifact([string]$Path, [byte[]]$Bytes, [string]$RelativePath, [string]$Type) {
    if ([IO.File]::Exists($Path)) { throw "ARTIFACT_EXISTS: $Path" }
    [IO.File]::WriteAllBytes($Path, $Bytes)
    [ordered]@{ path=$RelativePath; type=$Type; size=[long]$Bytes.Length; sha256=Get-F3BSha256Bytes $Bytes }
}

function New-F3BChangeBundle($Agent, [string[]]$Files, [string]$RunDirectory) {
    $patchResult = Invoke-F3BGit $Agent.worktree_absolute_path @('diff','--binary','--full-index','--no-ext-diff',$Agent.expected_head,'--')
    $patchBytes = $script:Utf8.GetBytes($patchResult.Stdout)
    $patch = Write-F3BBytesArtifact (Join-Path $RunDirectory "$($Agent.agent_id)-tracked.patch") $patchBytes "$($Agent.agent_id)-tracked.patch" 'tracked_patch'
    $untracked = @(Invoke-F3BGitNullList $Agent.worktree_absolute_path @('ls-files','--others','--exclude-standard','-z'))
    $entries = [Collections.Generic.List[object]]::new()
    foreach ($relative in ($untracked | Sort-Object)) {
        $bytes = [IO.File]::ReadAllBytes((Join-Path $Agent.worktree_absolute_path $relative))
        $digest = Get-F3BSha256Bytes $bytes
        $artifactRelative = "untracked/$digest.bin"
        $artifactPath = Join-Path $RunDirectory $artifactRelative
        if (-not [IO.File]::Exists($artifactPath)) {
            [void][IO.Directory]::CreateDirectory((Split-Path $artifactPath -Parent))
            [IO.File]::WriteAllBytes($artifactPath, $bytes)
        }
        $entries.Add([ordered]@{ path=$relative.Replace('\','/'); type='untracked'; size=[long]$bytes.Length; sha256=$digest; artifact=$artifactRelative })
    }
    $metadata = [ordered]@{ schema_version='1.0'; agent_id=$Agent.agent_id; baseline_sha=$Agent.expected_head; files=@($Files | Sort-Object); patch=$patch; untracked=@($entries) }
    $canonical = $metadata | ConvertTo-Json -Depth 20 -Compress
    $metadataPath = Join-Path $RunDirectory "$($Agent.agent_id)-change-metadata.json"
    [IO.File]::WriteAllText($metadataPath, $canonical, $script:Utf8)
    [ordered]@{ metadata=$metadata; metadata_sha256=Get-F3BFileSha256 $metadataPath; patch_sha256=$patch.sha256 }
}

function Write-F3BJson([string]$Path, $Value) {
    if ([IO.File]::Exists($Path) -or [IO.Directory]::Exists($Path)) { throw "ARTIFACT_EXISTS: $Path" }
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 40), $script:Utf8)
}

function Set-F3BJson([string]$Path, $Value) { [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 40), $script:Utf8) }

function New-F3BAgentStatus($Brief, $Agent) {
    [ordered]@{schema_version='1.0';task_id=$Brief.task_id;agent_id=$Agent.agent_id;planned_action=$Agent.disposition;started=$false;start_utc=$null;completed=$false;end_utc=$null;exit_code=$null;timed_out=$false;collected=$false;validation_stage='NOT_STARTED';success=$false;reason_code=$(if($Agent.disposition-ceq'SKIP'){'SKIPPED'}else{'NOT_STARTED'});error_summary='';preflight=$null;postflight=$null}
}

function Write-F3BAgentStatus([string]$RunDirectory, $Status) {
    $path=Join-Path $RunDirectory "$($Status.agent_id)-status.json"
    Set-F3BJson $path $Status
    if (-not ((Read-F3BUtf8 $path) | Test-Json -SchemaFile (Join-Path $script:SchemaRoot 'phase3b-agent-status.schema.json') -ErrorAction Stop)) { throw 'AGENT_STATUS_SCHEMA_INVALID' }
}

function Assert-F3BInputGate([string]$BriefPath,[string]$ApprovalFile,[string]$ExpectedDigest,[string]$TaskId){
    $approval=Read-F3BSchemaJson $ApprovalFile 'phase3b-write-approval.schema.json';$actual=Get-F3BFileSha256 $BriefPath
    if($actual-cne$ExpectedDigest-or$approval.task_id-cne$TaskId-or$approval.verdict-cne'APPROVE'-or$approval.task_brief_sha256.ToLowerInvariant()-cne$ExpectedDigest){throw 'TASK_BRIEF_OR_APPROVAL_CHANGED'}
}

function New-F3BAgentPrompt($Agent,$Brief,[string]$Role,[string]$RunDirectory,$PreState,$Delivery){
    [ordered]@{role=$Role;task_id=$Brief.task_id;agent_id=$Agent.agent_id;instructions=$Agent.instructions;report_path=(Join-Path $RunDirectory "$($Agent.agent_id)-report.json");report_schema=$(if($Role-ceq'REVIEW'){'phase3b-write-review-report.schema.json'}else{'phase3b-implementation-report.schema.json'});worktree=$Agent.worktree_absolute_path;git_top_level=$PreState.top_level;branch=$PreState.branch;pre_head=$PreState.head;allowed_files=@($Agent.allowed_files);test_commands=@($Agent.test_commands);fixed_delivery=$Delivery}|ConvertTo-Json -Depth 40 -Compress
}

function Start-F3BAgent($Agent, $Brief, [string]$RunDirectory, [string]$Executable, [string[]]$Prefix, [string]$Role, $Delivery) {
    $preState = Get-F3BGitState $Agent -RequireClean
    $reportPath = Join-Path $RunDirectory "$($Agent.agent_id)-report.json"
    $prompt = New-F3BAgentPrompt $Agent $Brief $Role $RunDirectory $preState $Delivery
    $args = @($Prefix) + @('exec','--ephemeral','--sandbox',$(if ($Agent.run_mode -ceq 'WRITE') {'workspace-write'} else {'read-only'}),'--cd',$Agent.worktree_absolute_path,'--color','never','--output-last-message',$reportPath,'-')
    $handle=Start-F3BProcess $Executable $args $Agent.worktree_absolute_path $prompt
    [pscustomobject]@{ Agent=$Agent; PreState=$preState; ReportPath=$reportPath; Handle=$handle; Role=$Role }
}

function Complete-F3BAgent($Attempt,[int]$TimeoutSeconds=600){
    $result=Complete-F3BProcess $Attempt.Handle $TimeoutSeconds
    $Attempt|Add-Member Process $result
    if($result.TimedOut){throw "AGENT_TIMEOUT: $($Attempt.Agent.agent_id)"};if($result.ExitCode-ne 0){throw "AGENT_FAILED: $($Attempt.Agent.agent_id)"}
    $report=Read-F3BSchemaJson $Attempt.ReportPath $(if($Attempt.Role-ceq'REVIEW'){'phase3b-write-review-report.schema.json'}else{'phase3b-implementation-report.schema.json'})
    $Attempt|Add-Member Report $report; $Attempt
}

function Get-F3BReason([string]$Message){$m=[regex]::Match($Message,'[A-Z][A-Z0-9_]+');if($m.Success){$m.Value}else{'UNCLASSIFIED_RUNTIME_ERROR'}}

function Get-F3BInventory([string]$Directory){
    @((Get-ChildItem -LiteralPath $Directory -File -Recurse|Sort-Object FullName|ForEach-Object{[ordered]@{path=[IO.Path]::GetRelativePath($Directory,$_.FullName).Replace('\','/');size=$_.Length;sha256=Get-F3BFileSha256 $_.FullName}}))
}

function Save-F3BProcessEvidence([string]$Directory,[string]$Id,$Result){
    $stdout=Write-F3BBytesArtifact (Join-Path $Directory "$Id-process-stdout.bin") $script:Utf8.GetBytes($Result.Stdout) "$Id-process-stdout.bin" 'stdout'
    $stderr=Write-F3BBytesArtifact (Join-Path $Directory "$Id-process-stderr.bin") $script:Utf8.GetBytes($Result.Stderr) "$Id-process-stderr.bin" 'stderr'
    Set-F3BJson (Join-Path $Directory "$Id-process.json") ([ordered]@{executable=$Result.FileName;argv=@($Result.Arguments);working_directory=$Result.WorkingDirectory;start_utc=$Result.StartedUtc.ToString('o');end_utc=$Result.EndedUtc.ToString('o');exit_code=$Result.ExitCode;timed_out=$Result.TimedOut;collected=$Result.Collected;stdout=$stdout;stderr=$stderr})
}

function Invoke-FairiesPhase3BWriteRuntime {
    $safeRunDirectory=$null;$runId=$null;$brief=$null;$digest=$null;$stage='PREFLIGHT';$bundleDigest=$null;$statuses=[ordered]@{};$active=$null
    trap {
        $runtimeFailure=$_
        if ($null -ne $safeRunDirectory -and [IO.Directory]::Exists($safeRunDirectory)) {
            try {
                $reason=Get-F3BReason $_.Exception.Message
                foreach($key in @($statuses.Keys)){$s=$statuses[$key];if(-not$s.success){$s.validation_stage=$stage;$s.reason_code=$reason;$s.error_summary=$_.Exception.Message;Write-F3BAgentStatus $safeRunDirectory $s}}
                $blocked = [ordered]@{ schema_version='1.0'; run_id=$runId; task_id=$brief.task_id; baseline_sha=$brief.baseline_sha; task_brief_sha256=$digest; stage=$stage; reason_code=$reason; safe_artifact_directory=$safeRunDirectory; artifact_bundle_sha256=$bundleDigest; final_result='BLOCKED' }
                $manifestPath = Join-Path $safeRunDirectory 'result-manifest.json'
                Set-F3BJson $manifestPath $blocked
                if(-not((Read-F3BUtf8 $manifestPath)|Test-Json -SchemaFile (Join-Path $script:SchemaRoot 'phase3b-result-manifest.schema.json') -ErrorAction Stop)){throw 'MANIFEST_SCHEMA_INVALID'}
            } catch { }
        }
        throw $runtimeFailure.Exception
    }
    if ([string]::IsNullOrWhiteSpace($TaskBriefPath) -or [string]::IsNullOrWhiteSpace($ApprovalPath)) { throw 'INPUT_PATH_REQUIRED' }
    $stage='INPUT_VALIDATION';$brief = Read-F3BSchemaJson $TaskBriefPath 'phase3b-write-task-brief.schema.json'
    $digest = Get-F3BFileSha256 $TaskBriefPath
    $candidateRoot = Assert-F3BSafeArtifactPath $RunsRoot @($script:KnownWorktrees + @($brief.agents.worktree_absolute_path))
    if (-not [IO.Directory]::Exists($candidateRoot)) { [void][IO.Directory]::CreateDirectory($candidateRoot) }
    $runId = '{0}-{1}' -f [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'), [Guid]::NewGuid().ToString('N')
    $runDirectory = Join-Path $candidateRoot $runId
    [void][IO.Directory]::CreateDirectory($runDirectory)
    $runDirectory = Assert-F3BSafeArtifactPath $runDirectory @($script:KnownWorktrees + @($brief.agents.worktree_absolute_path))
    $safeRunDirectory = $runDirectory
    [IO.File]::WriteAllBytes((Join-Path $runDirectory 'write-task-brief.json'), [IO.File]::ReadAllBytes($TaskBriefPath))
    [IO.File]::WriteAllBytes((Join-Path $runDirectory 'approval.json'), [IO.File]::ReadAllBytes($ApprovalPath))
    $schemaDigests=[ordered]@{}
    foreach($name in @('phase3b-agent-status.schema.json','phase3b-implementation-report.schema.json','phase3b-result-manifest.schema.json','phase3b-write-approval.schema.json','phase3b-write-review-report.schema.json','phase3b-write-task-brief.schema.json')){$source=Join-Path $script:SchemaRoot $name;$dest=Join-Path $runDirectory "schemas/$name";[void][IO.Directory]::CreateDirectory((Split-Path $dest -Parent));[IO.File]::WriteAllBytes($dest,[IO.File]::ReadAllBytes($source));$schemaDigests[$name]=Get-F3BFileSha256 $dest}
    foreach($agent in $brief.agents){$statuses[$agent.agent_id]=New-F3BAgentStatus $brief $agent;Write-F3BAgentStatus $runDirectory $statuses[$agent.agent_id]}
    $approval = Read-F3BSchemaJson $ApprovalPath 'phase3b-write-approval.schema.json'
    if ($approval.task_id -cne $brief.task_id -or $approval.verdict -cne 'APPROVE' -or $approval.task_brief_sha256.ToLowerInvariant() -cne $digest) { throw 'APPROVAL_MISMATCH' }
    Assert-F3BPlan $brief;$stage='PATH_VALIDATION'
    $workers = @($brief.agents | Where-Object { $_.agent_id -in @('backend','flutter') -and $_.disposition -ceq 'RUN' })
    $stage = 'WORKER_START'
    $attempts = [Collections.Generic.List[object]]::new()
    if ($brief.execution_strategy -ceq 'PARALLEL') {
        $failure=$null
        foreach($agent in $workers){try{Assert-F3BInputGate $TaskBriefPath $ApprovalPath $digest $brief.task_id;$a=Start-F3BAgent $agent $brief $runDirectory $CodexExecutable $CodexPrefixArgument 'IMPLEMENTATION' $null;$attempts.Add($a);$s=$statuses[$agent.agent_id];$s.started=$true;$s.start_utc=$a.Handle.StartedUtc.ToString('o');$s.preflight=$a.PreState;Write-F3BAgentStatus $runDirectory $s}catch{$failure=$_;break}}
        $stage='WORKER_COLLECTION'
        foreach($a in $attempts){try{$active=Complete-F3BAgent $a $AgentTimeoutSeconds;Save-F3BProcessEvidence $runDirectory $a.Agent.agent_id $active.Process;$s=$statuses[$a.Agent.agent_id];$s.completed=$true;$s.end_utc=$active.Process.EndedUtc.ToString('o');$s.exit_code=$active.Process.ExitCode;$s.timed_out=$active.Process.TimedOut;$s.collected=$true;Write-F3BAgentStatus $runDirectory $s}catch{$failure=$_;$s=$statuses[$a.Agent.agent_id];if($a.PSObject.Properties.Name-contains'Process'){Save-F3BProcessEvidence $runDirectory $a.Agent.agent_id $a.Process;$s.completed=$true;$s.end_utc=$a.Process.EndedUtc.ToString('o');$s.exit_code=$a.Process.ExitCode;$s.timed_out=$a.Process.TimedOut;$s.collected=$true};Write-F3BAgentStatus $runDirectory $s}}
        if($null-ne$failure){throw "PARALLEL_WORKER_FAILED: $($failure.Exception.Message)"}
    } else {
        foreach($id in $brief.sequential_order){$agent=$workers|Where-Object agent_id -CEQ $id;Assert-F3BInputGate $TaskBriefPath $ApprovalPath $digest $brief.task_id;$a=Start-F3BAgent $agent $brief $runDirectory $CodexExecutable $CodexPrefixArgument 'IMPLEMENTATION' $null;$attempts.Add($a);$s=$statuses[$id];$s.started=$true;$s.start_utc=$a.Handle.StartedUtc.ToString('o');$s.preflight=$a.PreState;Write-F3BAgentStatus $runDirectory $s;$stage='WORKER_COLLECTION';$active=Complete-F3BAgent $a $AgentTimeoutSeconds;Save-F3BProcessEvidence $runDirectory $id $active.Process;$s.completed=$true;$s.end_utc=$active.Process.EndedUtc.ToString('o');$s.exit_code=$active.Process.ExitCode;$s.timed_out=$active.Process.TimedOut;$s.collected=$true;Write-F3BAgentStatus $runDirectory $s;$stage='WORKER_START'}
    }
    $allFiles = [ordered]@{}
    $bundles = [ordered]@{}
    foreach ($agent in $workers) {
        $state = Get-F3BGitState $agent
        if ($state.head -cne $agent.expected_head -or $state.branch -cne $agent.branch) { throw 'POSTFLIGHT_GIT_CHANGED' }
        $allFiles[$agent.agent_id] = @(Get-F3BChangedFiles $agent)
        $attempt = $attempts | Where-Object { $_.Agent.agent_id -ceq $agent.agent_id }
        $bundles[$agent.agent_id] = New-F3BChangeBundle $agent $allFiles[$agent.agent_id] $runDirectory
    }
    $stage = 'TEST_EXECUTION'
    $testEvidence = [Collections.Generic.List[object]]::new()
    foreach ($agent in $workers) { foreach ($command in @($agent.test_commands)) {
        if ($command.network -or $command.external_service -or $command.device) { throw 'EXTERNAL_TEST_FORBIDDEN' }
        $logicalWd = Get-F3BFullPath $command.working_directory
        $physicalWd = Get-F3BPhysicalPath $logicalWd
        if (-not (Test-F3BInside $logicalWd $agent.worktree_absolute_path) -or -not (Test-F3BInside $physicalWd (Get-F3BPhysicalPath $agent.worktree_absolute_path))) { throw 'TEST_WORKING_DIRECTORY_ESCAPE' }
        $test = Invoke-F3BProcess $command.executable @($command.argv) $command.working_directory $command.timeout_seconds
        $stdoutBytes=$script:Utf8.GetBytes($test.Stdout);$stderrBytes=$script:Utf8.GetBytes($test.Stderr)
        $stdout=Write-F3BBytesArtifact (Join-Path $runDirectory "$($agent.agent_id)-$($command.command_id)-stdout.bin") $stdoutBytes "$($agent.agent_id)-$($command.command_id)-stdout.bin" 'stdout'
        $stderr=Write-F3BBytesArtifact (Join-Path $runDirectory "$($agent.agent_id)-$($command.command_id)-stderr.bin") $stderrBytes "$($agent.agent_id)-$($command.command_id)-stderr.bin" 'stderr'
        $testEvidence.Add([ordered]@{agent_id=$agent.agent_id;command_id=$command.command_id;executable=$command.executable;argv=@($command.argv);working_directory=$logicalWd;timeout_seconds=$command.timeout_seconds;started_utc=$test.StartedUtc.ToString('o');completed_utc=$test.EndedUtc.ToString('o');exit_code=$test.ExitCode;timed_out=$test.TimedOut;stdout=$stdout;stderr=$stderr})
        if($test.TimedOut){throw "TEST_TIMEOUT: $($command.command_id)"};if ($test.ExitCode -ne 0) { throw "TEST_FAILED: $($command.command_id)" }
    } }
    Set-F3BJson (Join-Path $runDirectory 'test-evidence.json') @($testEvidence)
    $stage='REPORT_VALIDATION'
    foreach($agent in $workers){$attempt=$attempts|Where-Object{$_.Agent.agent_id-ceq$agent.agent_id};$state=Get-F3BGitState $agent;Assert-F3BImplementationReport $attempt.Report $agent $brief.task_id $allFiles[$agent.agent_id] $attempt.PreState $state @($testEvidence);$s=$statuses[$agent.agent_id];$s.postflight=$state;$s.validation_stage=$stage;$s.success=$true;$s.reason_code='NONE';Write-F3BAgentStatus $runDirectory $s}
    $stage='ARTIFACT_GENERATION'
    $bundleObject=[ordered]@{schema_version='1.0';task_id=$brief.task_id;baseline_sha=$brief.baseline_sha;task_brief_sha256=$digest;agents=$bundles;tests=@($testEvidence)}
    $bundleText = $bundleObject | ConvertTo-Json -Depth 30 -Compress
    $bundleDigest = Get-F3BSha256Bytes $script:Utf8.GetBytes($bundleText)
    [IO.File]::WriteAllText((Join-Path $runDirectory 'change-bundle.json'), $bundleText, $script:Utf8)
    $gitEvidence=[ordered]@{};foreach($agent in $workers){$attempt=$attempts|Where-Object{$_.Agent.agent_id-ceq$agent.agent_id};$gitEvidence[$agent.agent_id]=[ordered]@{pre=$attempt.PreState;post=Get-F3BGitState $agent;changed_files=$allFiles[$agent.agent_id]}}
    Set-F3BJson (Join-Path $runDirectory 'git-evidence.json') $gitEvidence
    $inventory=Get-F3BInventory $runDirectory;Set-F3BJson (Join-Path $runDirectory 'artifact-inventory.json') $inventory;$inventoryDigest=Get-F3BFileSha256 (Join-Path $runDirectory 'artifact-inventory.json')
    $delivery=[ordered]@{task_brief=[ordered]@{path='write-task-brief.json';sha256=$digest};approval=[ordered]@{path='approval.json';sha256=Get-F3BFileSha256 (Join-Path $runDirectory 'approval.json')};schemas=$schemaDigests;change_bundle=[ordered]@{path='change-bundle.json';sha256=$bundleDigest};inventory=[ordered]@{path='artifact-inventory.json';sha256=$inventoryDigest};required_inputs=@($inventory.path)}
    Set-F3BJson (Join-Path $runDirectory 'review-fixed-inputs.json') $delivery
    $review=$brief.agents|Where-Object agent_id -CEQ test_review;$stage='REVIEW_START';Assert-F3BInputGate $TaskBriefPath $ApprovalPath $digest $brief.task_id
    $a=Start-F3BAgent $review $brief $runDirectory $CodexExecutable $CodexPrefixArgument 'REVIEW' $delivery;$s=$statuses.test_review;$s.started=$true;$s.start_utc=$a.Handle.StartedUtc.ToString('o');$s.preflight=$a.PreState;Write-F3BAgentStatus $runDirectory $s
    $stage='REVIEW_COLLECTION';$active=Complete-F3BAgent $a $AgentTimeoutSeconds;Save-F3BProcessEvidence $runDirectory 'test_review' $active.Process;$s.completed=$true;$s.end_utc=$active.Process.EndedUtc.ToString('o');$s.exit_code=$active.Process.ExitCode;$s.timed_out=$active.Process.TimedOut;$s.collected=$true
    $stage='REVIEW_VALIDATION';$rr=$active.Report
    if($rr.reviewer_agent_id-cne'test_review'-or$rr.task_id-cne$brief.task_id-or$rr.reviewed_artifact_sha256.ToLowerInvariant()-cne$bundleDigest){throw 'REVIEW_IDENTITY_OR_DIGEST_MISMATCH'}
    foreach($name in $schemaDigests.Keys){if($rr.reviewed_schema_sha256.$name-cne$schemaDigests[$name]){throw 'REVIEW_SCHEMA_DIGEST_MISMATCH'}}
    if(@($rr.acceptance_criteria_results|Where-Object result -CEQ 'FAIL').Count -or $rr.review_verdict -cne 'APPROVE' -or $rr.final_result -cne 'READY_FOR_PHASE3C' -or @($rr.findings|Where-Object severity -in @('BLOCKER','MAJOR')).Count){throw 'REVIEW_REJECTED'}
    $s.postflight=Get-F3BGitState $review -RequireClean;$s.validation_stage=$stage;$s.success=$true;$s.reason_code='NONE';Write-F3BAgentStatus $runDirectory $s
    $manifest = [ordered]@{ schema_version='1.0'; run_id=$runId; task_id=$brief.task_id; baseline_sha=$brief.baseline_sha; task_brief_sha256=$digest; stage='COMPLETE'; reason_code='NONE'; safe_artifact_directory=$runDirectory; artifact_bundle_sha256=$bundleDigest; final_result='READY_FOR_PHASE3C' }
    Write-F3BJson (Join-Path $runDirectory 'result-manifest.json') $manifest
    if(-not((Read-F3BUtf8 (Join-Path $runDirectory 'result-manifest.json'))|Test-Json -SchemaFile (Join-Path $script:SchemaRoot 'phase3b-result-manifest.schema.json') -ErrorAction Stop)){throw 'MANIFEST_SCHEMA_INVALID'}
    Set-F3BJson (Join-Path $runDirectory 'final-artifact-inventory.json') (Get-F3BInventory $runDirectory|Where-Object path -cne 'final-artifact-inventory.json')
    [pscustomobject]$manifest
}

if (-not $LibraryOnly) { Invoke-FairiesPhase3BWriteRuntime }
