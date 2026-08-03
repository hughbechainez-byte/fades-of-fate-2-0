#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $TaskName
)

$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    $root = & git rev-parse --show-toplevel
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($root)) {
        throw 'Not inside a Git repository.'
    }
    return $root.Trim()
}

function Get-BranchName([string] $TaskName) {
    $slug = ($TaskName -replace '[^A-Za-z0-9._-]+', '-').Trim('-').ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($slug)) {
        throw 'Task name did not produce a valid branch slug.'
    }
    return "codex/$slug"
}

$repoRoot = Get-RepoRoot
Push-Location $repoRoot
try {
    & git fetch --all --prune
    if ($LASTEXITCODE -ne 0) { throw 'git fetch failed.' }

    $currentBranch = (& git branch --show-current).Trim()
    $statusText = & git status --porcelain=v1 --untracked-files=normal
    $isDirty = [bool]($statusText)
    $branchName = Get-BranchName $TaskName
    $baseCommit = (& git rev-parse origin/main).Trim()

    & git show-ref --verify --quiet "refs/heads/$branchName" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        throw "Branch already exists: $branchName"
    }

    if ($currentBranch -eq $branchName) {
        if ($isDirty) {
            throw "Current worktree is already on $branchName but it is dirty."
        }
        Write-Output "BRANCH=$branchName"
        Write-Output "BASE_COMMIT=$baseCommit"
        Write-Output "WORKTREE_PATH=$repoRoot"
        Write-Output 'REUSED_CURRENT_WORKTREE=1'
        return
    }

    if ($currentBranch -ne 'main' -and -not $isDirty) {
        & git switch -c $branchName origin/main
        if ($LASTEXITCODE -ne 0) { throw "Unable to create $branchName in the current worktree." }
        Write-Output "BRANCH=$branchName"
        Write-Output "BASE_COMMIT=$baseCommit"
        Write-Output "WORKTREE_PATH=$repoRoot"
        Write-Output 'REUSED_CURRENT_WORKTREE=1'
        return
    }

    $worktreeBase = Join-Path (Split-Path -Parent $repoRoot) 'codex-worktrees'
    $safeName = $branchName.Substring(6)
    $targetPath = Join-Path $worktreeBase $safeName
    if (Test-Path -LiteralPath $targetPath) {
        throw "Target worktree path already exists: $targetPath"
    }

    New-Item -ItemType Directory -Path $worktreeBase -Force | Out-Null
    & git worktree add -b $branchName $targetPath origin/main
    if ($LASTEXITCODE -ne 0) { throw "Unable to create worktree at $targetPath." }

    Write-Output "BRANCH=$branchName"
    Write-Output "BASE_COMMIT=$baseCommit"
    Write-Output "WORKTREE_PATH=$targetPath"
    Write-Output 'REUSED_CURRENT_WORKTREE=0'
}
finally {
    Pop-Location
}
