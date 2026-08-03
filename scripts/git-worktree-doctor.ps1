#requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    $root = & git rev-parse --show-toplevel
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($root)) {
        throw 'Not inside a Git repository.'
    }
    return $root.Trim()
}

function Parse-Worktrees([string[]] $Lines) {
    $records = New-Object System.Collections.Generic.List[object]
    $current = $null

    foreach ($line in $Lines) {
        if ($line -like 'worktree *') {
            if ($null -ne $current) {
                $records.Add([pscustomobject]$current)
            }
            $current = [ordered]@{
                Path = $line.Substring(9)
                Head = ''
                Branch = ''
                Detached = $false
                Prunable = $false
                Locked = $false
            }
            continue
        }

        if ($null -eq $current) {
            continue
        }

        if ($line -like 'HEAD *') {
            $current.Head = $line.Substring(5)
        }
        elseif ($line -like 'branch *') {
            $current.Branch = $line.Substring(7)
        }
        elseif ($line -eq 'detached') {
            $current.Detached = $true
            if ([string]::IsNullOrWhiteSpace($current.Branch)) {
                $current.Branch = 'detached'
            }
        }
        elseif ($line -eq 'prunable') {
            $current.Prunable = $true
        }
        elseif ($line -eq 'locked') {
            $current.Locked = $true
        }
    }

    if ($null -ne $current) {
        $records.Add([pscustomobject]$current)
    }

    return $records
}

$repoRoot = Get-RepoRoot
$worktreeLines = & git worktree list --porcelain
$worktrees = Parse-Worktrees $worktreeLines
$originMainExists = $true
& git show-ref --verify --quiet refs/remotes/origin/main | Out-Null
if ($LASTEXITCODE -ne 0) {
    $originMainExists = $false
}

$mainOwners = @()
$dirtyWorktrees = @()
$unsafe = $false

Write-Output "REPO_ROOT=$repoRoot"

foreach ($worktree in $worktrees) {
    $path = [IO.Path]::GetFullPath($worktree.Path)
    $exists = Test-Path -LiteralPath $path
    $branch = if ([string]::IsNullOrWhiteSpace($worktree.Branch)) { 'detached' } else { $worktree.Branch }
    $stale = $worktree.Prunable -or -not $exists
    if ($branch -eq 'refs/heads/main') {
        $mainOwners += $path
    }

    $dirty = $false
    $behind = $null
    $ahead = $null
    if ($exists) {
        $dirty = [bool](@(& git -C $path status --porcelain=v1 --untracked-files=normal))
        if ($dirty) {
            $dirtyWorktrees += $path
            if ($branch -eq 'refs/heads/main') {
                $unsafe = $true
            }
        }
        if ($originMainExists) {
            $relation = & git -C $path rev-list --left-right --count origin/main...HEAD
            if ($relation -match '^\s*(\d+)\s+(\d+)\s*$') {
                $behind = [int]$Matches[1]
                $ahead = [int]$Matches[2]
                if ($branch -ne 'refs/heads/main' -and ($behind -gt 0 -or $ahead -gt 0)) {
                    Write-Warning "$path is $behind behind and $ahead ahead of origin/main."
                    if ($behind -gt 0) {
                        $unsafe = $true
                    }
                }
            }
        }
    }

    if ($stale) {
        Write-Warning "Stale worktree registration: $path"
        $unsafe = $true
    }

    $leaf = Split-Path -Leaf $path
    if ($leaf -eq 'The Fades of Fate Demo' -and $branch -ne 'detached') {
        Write-Warning "Packaged Desktop output is registered as a source worktree: $path"
        $unsafe = $true
    }

    Write-Output ("WORKTREE path={0} branch={1} head={2} dirty={3} stale={4} behind={5} ahead={6}" -f $path, $branch, $worktree.Head, $dirty, $stale, ($behind -as [string]), ($ahead -as [string]))
}

if ($mainOwners.Count -ne 1) {
    Write-Warning "Expected exactly one worktree on main, found $($mainOwners.Count)."
    $unsafe = $true
}
elseif ($mainOwners.Count -eq 1) {
    Write-Output "MAIN_OWNER=$($mainOwners[0])"
}

if ($dirtyWorktrees.Count -gt 1) {
    Write-Warning "Multiple dirty worktrees detected: $($dirtyWorktrees.Count)"
    $unsafe = $true
}

if ($dirtyWorktrees.Count -eq 1) {
    Write-Output "DIRTY_WORKTREE=$($dirtyWorktrees[0])"
}

if ($unsafe) {
    exit 1
}
