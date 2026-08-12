#requires -Version 5.1
[CmdletBinding()]
param(
    [string] $TaskBranch = ''
)

$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    $root = & git rev-parse --show-toplevel
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($root)) {
        throw 'Not inside a Git repository.'
    }
    return $root.Trim()
}

function Get-MainWorktreePath {
    $lines = & git worktree list --porcelain
    $currentPath = $null
    $currentBranch = $null
    foreach ($line in $lines) {
        if ($line -like 'worktree *') {
            if ($currentBranch -eq 'refs/heads/main') {
                return [IO.Path]::GetFullPath($currentPath)
            }
            $currentPath = $line.Substring(9)
            $currentBranch = $null
            continue
        }
        if ($line -like 'branch *') {
            $currentBranch = $line.Substring(7)
        }
    }
    if ($currentBranch -eq 'refs/heads/main') {
        return [IO.Path]::GetFullPath($currentPath)
    }
    throw 'No worktree owns main.'
}

$repoRoot = Get-RepoRoot
Push-Location $repoRoot
try {
    & git fetch --all --prune
    if ($LASTEXITCODE -ne 0) { throw 'Initial fetch failed.' }

    if ([string]::IsNullOrWhiteSpace($TaskBranch)) {
        $TaskBranch = (& git branch --show-current).Trim()
    }

    if ([string]::IsNullOrWhiteSpace($TaskBranch)) {
        throw 'No task branch was supplied and the current worktree is detached.'
    }

    if ($TaskBranch -eq 'main') {
        throw 'Refusing to finish from the main branch.'
    }

    $statusText = & git status --porcelain=v1 --untracked-files=normal
    if ($statusText) {
        throw "Task branch $TaskBranch is dirty. Commit or clean it before finishing."
    }

    $originMain = (& git rev-parse origin/main).Trim()
    $relation = & git rev-list --left-right --count origin/main...HEAD
    if ($relation -match '^\s*(\d+)\s+(\d+)\s*$') {
        $behind = [int]$Matches[1]
        $ahead = [int]$Matches[2]
        if ($behind -gt 0) {
            Write-Output "REBASE_NEEDED=1"
            & git rebase origin/main
            if ($LASTEXITCODE -ne 0) {
                throw 'Task branch rebase failed.'
            }
        }
        elseif ($ahead -eq 0) {
            throw 'Task branch has no commits ahead of origin/main.'
        }
    }

    $taskBuild = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot 'tools\Build-Windows.ps1') -SkipDesktopInstall -VisualReviewApproved
    if ($LASTEXITCODE -ne 0) {
        throw 'Task branch Windows build failed.'
    }
    $taskBuild | ForEach-Object { Write-Output $_ }

    & git fetch --all --prune
    if ($LASTEXITCODE -ne 0) { throw 'Refresh fetch failed.' }

    $mainWorktree = Get-MainWorktreePath
    Push-Location $mainWorktree
    try {
        & git fetch --all --prune
        if ($LASTEXITCODE -ne 0) { throw 'Main worktree fetch failed.' }

        & git switch main
        if ($LASTEXITCODE -ne 0) { throw 'Unable to switch the canonical worktree to main.' }

        $mainBefore = (& git rev-parse HEAD).Trim()
        & git pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) { throw 'Main worktree could not fast-forward to origin/main.' }
        $mainAfterPull = (& git rev-parse HEAD).Trim()
        if ($mainBefore -ne $mainAfterPull) {
            Write-Output "MAIN_ADVANCED=1"
        }

        & git merge --ff-only $TaskBranch
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to fast-forward main to $TaskBranch."
        }

        $finalMainSha = (& git rev-parse HEAD).Trim()
        $buildOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $mainWorktree 'tools\Build-Windows.ps1') -VisualReviewApproved
        if ($LASTEXITCODE -ne 0) {
            throw 'Final Windows build failed.'
        }
        $buildOutput | ForEach-Object { Write-Output $_ }

        & git push origin main
        if ($LASTEXITCODE -ne 0) { throw 'Push to origin/main failed.' }

        $remoteMainSha = (& git ls-remote origin refs/heads/main | ForEach-Object { ($_ -split '\s+')[0] }).Trim()
        $finalBuildMetadata = Join-Path $mainWorktree 'dist\The Fades of Fate\BUILD_SOURCE_COMMIT.txt'
        $desktopBuild = [Environment]::GetFolderPath('Desktop')
        $desktopDemo = Join-Path $desktopBuild 'The Fades of Fate Demo'

        Write-Output "FINAL_MAIN_SHA=$finalMainSha"
        Write-Output "REMOTE_MAIN_SHA=$remoteMainSha"
        Write-Output "BUILD_METADATA=$finalBuildMetadata"
        Write-Output "DESKTOP_BUILD=$desktopDemo"
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}
