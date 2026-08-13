[CmdletBinding()]
param(
    [string]$OutputRoot = "C:\Users\blowb\Desktop\FoF2_Underpass_FreeWalk"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputRoot)
$pakPath = Join-Path $repoRoot "build\underpass_freewalk\UnderpassFreeWalk.pak"
$runtimePath = Join-Path $repoRoot "openbor\runtime\OpenBOR.exe"

Push-Location $repoRoot
try {
    & python tools\Build-Underpass-FreeWalk.py
    if ($LASTEXITCODE -ne 0) { throw "Underpass free-walk build failed." }
    if (-not (Test-Path $pakPath)) { throw "UnderpassFreeWalk.pak was not produced." }
    if (-not (Test-Path $runtimePath)) { throw "Pinned OpenBOR runtime was not found." }

    New-Item -ItemType Directory -Force -Path $outputPath, (Join-Path $outputPath "Paks"), (Join-Path $outputPath "Logs"), (Join-Path $outputPath "Saves"), (Join-Path $outputPath "ScreenShots") | Out-Null
    $looseDataPath = Join-Path $outputPath "data"
    if (Test-Path $looseDataPath) {
        $legacyDataPath = Join-Path $outputPath ("_legacy_data_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
        Move-Item -LiteralPath $looseDataPath -Destination $legacyDataPath
    }
    Copy-Item -LiteralPath $runtimePath -Destination (Join-Path $outputPath "OpenBOR.exe") -Force
    Copy-Item -LiteralPath $pakPath -Destination (Join-Path $outputPath "Paks\UnderpassFreeWalk.pak") -Force
    Copy-Item -LiteralPath (Join-Path $repoRoot "openbor\runtime\OPENBOR-LICENSE.txt") -Destination $outputPath -Force
    Copy-Item -LiteralPath (Join-Path $repoRoot "openbor\runtime\OPENBOR-README.txt") -Destination $outputPath -Force
    @"
Fades of Fate 2.0 - Underpass Free Walk

Run Launch_Underpass_FreeWalk.cmd. The launcher starts OpenBOR from this folder so ./Paks is resolved correctly.
Controls: arrows move, Ctrl attacks, Alt jumps, Enter starts.
"@ | Set-Content -LiteralPath (Join-Path $outputPath "READ_ME_FIRST.txt") -Encoding UTF8
    @"
@echo off
cd /d "%~dp0"
OpenBOR.exe
"@ | Set-Content -LiteralPath (Join-Path $outputPath "Launch_Underpass_FreeWalk.cmd") -Encoding ASCII

    $process = Start-Process -FilePath (Join-Path $outputPath "OpenBOR.exe") -WorkingDirectory $outputPath -PassThru
    Start-Sleep -Seconds 8
    if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        throw "Underpass free-walk executable exited during launch verification."
    }
    Stop-Process -Id $process.Id -Force
} finally {
    Pop-Location
}

Write-Output "Underpass free-walk demo ready: $outputPath"
Write-Output "Launcher: $(Join-Path $outputPath 'Launch_Underpass_FreeWalk.cmd')"
