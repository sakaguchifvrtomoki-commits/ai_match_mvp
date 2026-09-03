[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$TaskDirectory,

    [ValidateRange(1, 3600)]
    [int]$AgentTimeoutSeconds = 600
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$taskDirectoryPath = [IO.Path]::GetFullPath($TaskDirectory)

if (-not [IO.Directory]::Exists($taskDirectoryPath)) {
    throw "TASK_DIRECTORY_MISSING: $taskDirectoryPath"
}

$taskBriefs = @(
    Get-ChildItem -LiteralPath $taskDirectoryPath -File |
        Where-Object { $_.Name -like '*task-brief.json' }
)

$approvals = @(
    Get-ChildItem -LiteralPath $taskDirectoryPath -File |
        Where-Object { $_.Name -like '*approval.json' }
)

if ($taskBriefs.Count -ne 1) {
    throw "TASK_BRIEF_COUNT_INVALID: expected 1, found $($taskBriefs.Count)"
}

if ($approvals.Count -ne 1) {
    throw "APPROVAL_COUNT_INVALID: expected 1, found $($approvals.Count)"
}

$runtime = Join-Path $PSScriptRoot 'Invoke-FairiesWritePipeline.ps1'

if (-not [IO.File]::Exists($runtime)) {
    throw "WRITE_RUNTIME_MISSING: $runtime"
}

& $runtime `
    -TaskBriefPath $taskBriefs[0].FullName `
    -ApprovalPath $approvals[0].FullName `
    -AgentTimeoutSeconds $AgentTimeoutSeconds