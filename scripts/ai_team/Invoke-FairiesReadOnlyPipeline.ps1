#requires -Version 7.0

<#
.SYNOPSIS
Runs the Fairies Orchestrator and Test/Review agents sequentially in read-only mode.

.DESCRIPTION
The human goal is saved verbatim outside both worktrees. Do not include secrets in
HumanGoal. This script does not detect, reject, or mask secrets.

.PARAMETER HumanGoal
One development goal. The value is written verbatim to the run record and prompts.

.PARAMETER OrchestratorExpectedHeadSha
Required full (40 hexadecimal character) HEAD SHA for the Orchestrator worktree.

.PARAMETER TestReviewExpectedHeadSha
Required full (40 hexadecimal character) HEAD SHA for the Test/Review worktree.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$HumanGoal,

    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$OrchestratorExpectedHeadSha,

    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$TestReviewExpectedHeadSha,

    [ValidateNotNullOrEmpty()]
    [string]$OrchestratorWorktree = 'C:\Users\sakag\other\fairies-orchestrator',

    [ValidateNotNullOrEmpty()]
    [string]$OrchestratorExpectedBranch = 'agent/orchestrator',

    [ValidateNotNullOrEmpty()]
    [string]$TestReviewWorktree = 'C:\Users\sakag\other\fairies-test',

    [ValidateNotNullOrEmpty()]
    [string]$TestReviewExpectedBranch = 'agent/test-review',

    [ValidateNotNullOrEmpty()]
    [string]$RunsRoot = 'C:\Users\sakag\other\fairies-ai-runs'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Utf8NoBom = [System.Text.UTF8Encoding]::new($false, $true)

function Get-NormalizedPath {
    param([Parameter(Mandatory)][string]$Path)

    return [System.IO.Path]::GetFullPath($Path).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
}

function Get-PhysicalPath {
    param([Parameter(Mandatory)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($fullPath)
    $relativePath = [System.IO.Path]::GetRelativePath($root, $fullPath)
    $physicalPath = $root

    foreach ($segment in $relativePath.Split(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.StringSplitOptions]::RemoveEmptyEntries
    )) {
        $physicalPath = [System.IO.Path]::Combine($physicalPath, $segment)
        if (-not [System.IO.Directory]::Exists($physicalPath)) {
            continue
        }

        $directory = [System.IO.DirectoryInfo]::new($physicalPath)
        if (($directory.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) {
            # A normal directory keeps the current physical prefix unchanged.
            continue
        }

        # Junctions and directory symbolic links are both reparse points. Resolve
        # their final targets before evaluating any following path segments.
        $target = $directory.ResolveLinkTarget($true)
        if ($null -eq $target -or $target -isnot [System.IO.DirectoryInfo]) {
            throw "Could not resolve directory link in path: $physicalPath"
        }
        # The returned target can itself contain linked parent components, so run
        # it through the same component-wise physical resolution before continuing.
        $physicalPath = Get-PhysicalPath $target.FullName
    }

    # If a suffix does not exist yet, it remains appended to the physical path of
    # the longest existing parent. A post-creation check closes that boundary.
    return Get-NormalizedPath $physicalPath
}

function Test-PathInside {
    param(
        [Parameter(Mandatory)][string]$Candidate,
        [Parameter(Mandatory)][string]$Container
    )

    $candidatePath = Get-NormalizedPath $Candidate
    $containerPath = Get-NormalizedPath $Container
    if ($candidatePath.Equals($containerPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }

    $prefix = $containerPath + [System.IO.Path]::DirectorySeparatorChar
    return $candidatePath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Invoke-GitInspection {
    param(
        [Parameter(Mandatory)][string]$Worktree,
        [Parameter(Mandatory)]
        [ValidateSet('TopLevel', 'Branch', 'Head', 'Status')]
        [string]$Inspection
    )

    $arguments = [System.Collections.Generic.List[string]]::new()
    $arguments.Add('-C')
    $arguments.Add($Worktree)
    switch ($Inspection) {
        'TopLevel' {
            $arguments.Add('rev-parse')
            $arguments.Add('--show-toplevel')
        }
        'Branch' {
            $arguments.Add('symbolic-ref')
            $arguments.Add('--quiet')
            $arguments.Add('--short')
            $arguments.Add('HEAD')
        }
        'Head' {
            $arguments.Add('rev-parse')
            $arguments.Add('--verify')
            $arguments.Add('HEAD')
        }
        'Status' {
            $arguments.Add('status')
            $arguments.Add('--porcelain=v1')
            $arguments.Add('--untracked-files=all')
        }
    }

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'git'
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in $arguments) {
        [void]$startInfo.ArgumentList.Add($argument)
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "Git inspection '$Inspection' could not be started for '$Worktree'."
        }
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "Git inspection '$Inspection' failed for '$Worktree' (exit $($process.ExitCode)): $stderr"
        }
        return $stdout.TrimEnd("`r", "`n")
    }
    finally {
        $process.Dispose()
    }
}

function Assert-WorktreeState {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$Worktree,
        [Parameter(Mandatory)][string]$ExpectedBranch,
        [Parameter(Mandatory)][string]$ExpectedHeadSha
    )

    if (-not [System.IO.Directory]::Exists($Worktree)) {
        throw "$Label worktree does not exist: $Worktree"
    }

    $normalizedWorktree = Get-NormalizedPath (Resolve-Path -LiteralPath $Worktree).Path
    $topLevel = Invoke-GitInspection -Worktree $normalizedWorktree -Inspection TopLevel
    if (-not (Get-NormalizedPath $topLevel).Equals($normalizedWorktree, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label Git top-level mismatch. Expected '$normalizedWorktree'; actual '$topLevel'."
    }

    $branch = Invoke-GitInspection -Worktree $normalizedWorktree -Inspection Branch
    if ($branch -cne $ExpectedBranch) {
        throw "$Label branch mismatch or detached HEAD. Expected '$ExpectedBranch'; actual '$branch'."
    }

    $head = Invoke-GitInspection -Worktree $normalizedWorktree -Inspection Head
    if ($head -cne $ExpectedHeadSha.ToLowerInvariant()) {
        throw "$Label HEAD mismatch. Expected '$ExpectedHeadSha'; actual '$head'."
    }

    $status = Invoke-GitInspection -Worktree $normalizedWorktree -Inspection Status
    if ($status.Length -ne 0) {
        throw "$Label worktree is dirty: $status"
    }

    return [pscustomobject]@{
        Label    = $Label
        Worktree = $normalizedWorktree
        Branch   = $branch
        Head     = $head
        Status   = $status
    }
}

function Assert-StateUnchanged {
    param([Parameter(Mandatory)][pscustomobject]$Baseline)

    $current = Assert-WorktreeState `
        -Label $Baseline.Label `
        -Worktree $Baseline.Worktree `
        -ExpectedBranch $Baseline.Branch `
        -ExpectedHeadSha $Baseline.Head
    if ($current.Status -cne $Baseline.Status) {
        throw "$($Baseline.Label) status changed during the pipeline."
    }
}

function Read-RequiredUtf8File {
    param([Parameter(Mandatory)][string]$Path)

    if (-not [System.IO.File]::Exists($Path)) {
        throw "Required output file does not exist: $Path"
    }
    $item = Get-Item -LiteralPath $Path
    if ($item.PSIsContainer -or $item.Length -le 0) {
        throw "Required output is not a non-empty regular file: $Path"
    }
    try {
        return [System.IO.File]::ReadAllText($item.FullName, $script:Utf8NoBom)
    }
    catch {
        throw "Required output is not valid UTF-8: $Path. $($_.Exception.Message)"
    }
}

function Get-FinalNonEmptyLine {
    param([Parameter(Mandatory)][string]$Text)

    $lines = $Text -split "`r`n|`n|`r"
    for ($index = $lines.Count - 1; $index -ge 0; $index--) {
        if ($lines[$index].Length -gt 0) {
            return $lines[$index]
        }
    }
    return $null
}

function Invoke-CodexReadOnly {
    param(
        [Parameter(Mandatory)][string]$CodexPath,
        [Parameter(Mandatory)][string]$Worktree,
        [Parameter(Mandatory)][string]$Prompt,
        [Parameter(Mandatory)][string]$OutputPath
    )

    if ([System.IO.File]::Exists($OutputPath) -or [System.IO.Directory]::Exists($OutputPath)) {
        throw "Refusing to overwrite output path: $OutputPath"
    }

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $CodexPath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardInputEncoding = $script:Utf8NoBom
    $startInfo.StandardOutputEncoding = $script:Utf8NoBom
    $startInfo.StandardErrorEncoding = $script:Utf8NoBom
    foreach ($argument in @(
        'exec', '--ephemeral', '--sandbox', 'read-only',
        '--cd', $Worktree, '--color', 'never', '--output-last-message', $OutputPath, '-'
    )) {
        [void]$startInfo.ArgumentList.Add($argument)
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "Codex CLI could not be started for '$Worktree'."
        }
        $process.StandardInput.Write($Prompt)
        $process.StandardInput.Close()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "Codex CLI failed for '$Worktree' (exit $($process.ExitCode)). Standard error: $stderr"
        }
        if ($stdout.Length -gt 0) {
            Write-Verbose $stdout
        }
    }
    finally {
        $process.Dispose()
    }
}

if ($OrchestratorExpectedHeadSha -cnotmatch '^[0-9a-fA-F]{40}$' -or
    $TestReviewExpectedHeadSha -cnotmatch '^[0-9a-fA-F]{40}$') {
    throw 'Both Expected HEAD values must be independent full 40-character hexadecimal SHAs.'
}

$orchestratorBaseline = Assert-WorktreeState `
    -Label 'Orchestrator' `
    -Worktree $OrchestratorWorktree `
    -ExpectedBranch $OrchestratorExpectedBranch `
    -ExpectedHeadSha $OrchestratorExpectedHeadSha
$testReviewBaseline = Assert-WorktreeState `
    -Label 'Test/Review' `
    -Worktree $TestReviewWorktree `
    -ExpectedBranch $TestReviewExpectedBranch `
    -ExpectedHeadSha $TestReviewExpectedHeadSha

$normalizedRunsRoot = Get-NormalizedPath $RunsRoot
$physicalRunsRoot = Get-PhysicalPath $normalizedRunsRoot
foreach ($worktree in @($orchestratorBaseline.Worktree, $testReviewBaseline.Worktree)) {
    $physicalWorktree = Get-PhysicalPath $worktree
    if (Test-PathInside -Candidate $physicalRunsRoot -Container $physicalWorktree) {
        throw "RunsRoot must resolve outside both worktrees: $physicalRunsRoot"
    }
}

$codexCommandPaths = @(
    Get-Command -Name 'codex.cmd' -CommandType Application -All -ErrorAction SilentlyContinue |
        ForEach-Object { [System.IO.Path]::GetFullPath($_.Source) } |
        Sort-Object -Unique
)
if ($codexCommandPaths.Count -eq 0) {
    throw 'Codex CLI could not be resolved: codex.cmd was not found on PATH.'
}
if ($codexCommandPaths.Count -gt 1) {
    throw "Codex CLI resolution is ambiguous: multiple codex.cmd files were found on PATH: $($codexCommandPaths -join ', ')"
}
$codexPath = $codexCommandPaths[0]
if (-not [System.IO.File]::Exists($codexPath)) {
    throw "Resolved Codex CLI does not exist: $codexPath"
}

if (-not [System.IO.Directory]::Exists($normalizedRunsRoot)) {
    [void](New-Item -ItemType Directory -Path $normalizedRunsRoot)
}
$runId = '{0}-{1}' -f [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'), [Guid]::NewGuid().ToString('N')
$runDirectory = Join-Path $normalizedRunsRoot $runId
if ([System.IO.File]::Exists($runDirectory) -or [System.IO.Directory]::Exists($runDirectory)) {
    throw "Run directory collision: $runDirectory"
}
[void](New-Item -ItemType Directory -Path $runDirectory)

# Re-resolve after creation so a newly materialized normal directory, junction,
# or symbolic-link boundary cannot redirect record writes into either worktree.
$physicalRunDirectory = Get-PhysicalPath $runDirectory
foreach ($worktree in @($orchestratorBaseline.Worktree, $testReviewBaseline.Worktree)) {
    $physicalWorktree = Get-PhysicalPath $worktree
    if (Test-PathInside -Candidate $physicalRunDirectory -Container $physicalWorktree) {
        throw "Run directory must resolve outside both worktrees: $physicalRunDirectory"
    }
}

$humanGoalPath = Join-Path $physicalRunDirectory 'human-goal.txt'
$taskBriefPath = Join-Path $physicalRunDirectory 'task-brief.txt'
$reviewPath = Join-Path $physicalRunDirectory 'test-review.txt'
[System.IO.File]::WriteAllText($humanGoalPath, $HumanGoal, $script:Utf8NoBom)

Write-Host "Run ID: $runId"
Write-Host "Human Goal: $humanGoalPath"
Write-Host "Task Brief: $taskBriefPath"
Write-Host "Review Result: $reviewPath"

$orchestratorPrompt = @"
You are the Fairies Orchestrator Agent. Work in READ ONLY mode.
Human Goal follows verbatim between markers:
--- HUMAN GOAL BEGIN ---
$HumanGoal
--- HUMAN GOAL END ---

Runtime baseline:
- Orchestrator worktree: $($orchestratorBaseline.Worktree)
- Orchestrator branch: $($orchestratorBaseline.Branch)
- Orchestrator HEAD: $($orchestratorBaseline.Head)
- Test/Review worktree: $($testReviewBaseline.Worktree)
- Test/Review branch: $($testReviewBaseline.Branch)
- Test/Review HEAD: $($testReviewBaseline.Head)

Read AGENTS.md, docs/ai_development_team_rules.md,
docs/ai_team/orchestrator_guide.md, and docs/ai_team/task_brief_template.md.
Return a complete Task Brief in the official template format. Include worktree,
branch, Start commit SHA, RUN mode, allowed/forbidden files, objective acceptance
criteria, dependencies, handoff, integration order, and human verification.
Do not change any file, Git state/history, branch, or worktree. Do not commit,
merge, or run repository tests. Do not start another agent or access real Google
Drive. If the brief is safe and executable, make the final non-empty line exactly:
TASK BRIEF: READY
Otherwise make the final non-empty line exactly:
TASK BRIEF: BLOCKED
"@

try {
    Invoke-CodexReadOnly `
        -CodexPath $codexPath `
        -Worktree $orchestratorBaseline.Worktree `
        -Prompt $orchestratorPrompt `
        -OutputPath $taskBriefPath
}
finally {
    Assert-StateUnchanged -Baseline $orchestratorBaseline
    Assert-StateUnchanged -Baseline $testReviewBaseline
}

$taskBrief = Read-RequiredUtf8File -Path $taskBriefPath
$taskBriefGate = Get-FinalNonEmptyLine -Text $taskBrief
if ($taskBriefGate -cne 'TASK BRIEF: READY') {
    throw "Task Brief gate stopped the pipeline. Final non-empty line: '$taskBriefGate'"
}

$reviewPrompt = @"
You are the Fairies Test/Review Agent. Perform an independent READ ONLY review.
The saved Task Brief is: $taskBriefPath
Review the exact UTF-8 content below:
--- TASK BRIEF BEGIN ---
$taskBrief
--- TASK BRIEF END ---

Runtime review baseline:
- Test/Review worktree: $($testReviewBaseline.Worktree)
- Test/Review branch: $($testReviewBaseline.Branch)
- Test/Review HEAD: $($testReviewBaseline.Head)
- Orchestrator worktree: $($orchestratorBaseline.Worktree)
- Orchestrator branch: $($orchestratorBaseline.Branch)
- Orchestrator HEAD: $($orchestratorBaseline.Head)

Check the Task Brief against AGENTS.md, the AI team rules, Orchestrator Guide,
and Task Brief template. Report severity, location, reproduction condition, and
expected result for every finding. Do not change files, Git state/history,
branches, or worktrees. Do not commit, merge, run repository tests, start other
agents, or access real Google Drive. End with exactly one standalone final
non-empty line: APPROVE when no changes are required, otherwise REQUEST CHANGES.
Only that final non-empty line is machine evaluated.
"@

try {
    Invoke-CodexReadOnly `
        -CodexPath $codexPath `
        -Worktree $testReviewBaseline.Worktree `
        -Prompt $reviewPrompt `
        -OutputPath $reviewPath
}
finally {
    Assert-StateUnchanged -Baseline $orchestratorBaseline
    Assert-StateUnchanged -Baseline $testReviewBaseline
}

$review = Read-RequiredUtf8File -Path $reviewPath
$reviewGate = Get-FinalNonEmptyLine -Text $review
switch -CaseSensitive ($reviewGate) {
    'APPROVE' {
        Write-Host 'Final Gate: APPROVE'
    }
    'REQUEST CHANGES' {
        Write-Host 'Final Gate: REQUEST CHANGES'
        throw 'The Test/Review Agent requested changes.'
    }
    default {
        Write-Host 'Final Gate: INDETERMINATE'
        throw "Unrecognized review gate. Final non-empty line: '$reviewGate'"
    }
}

[pscustomobject]@{
    RunId          = $runId
    HumanGoalPath  = $humanGoalPath
    TaskBriefPath  = $taskBriefPath
    ReviewPath     = $reviewPath
    FinalGate      = $reviewGate
}
