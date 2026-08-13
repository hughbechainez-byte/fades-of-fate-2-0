[CmdletBinding()]
param(
    [string]$OutputRoot = "C:\Users\blowb\Desktop\Fades of Fate 2.0 - Sunset Underpass Tech Demo"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputRoot)
$pakPath = Join-Path $repoRoot "build\underpass_techdemo\UnderpassTechDemo.pak"
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
    Get-ChildItem -LiteralPath (Join-Path $outputPath "Paks") -Filter "*.pak" -File | Where-Object { $_.Name -ne "UnderpassTechDemo.pak" } | ForEach-Object {
        $legacyPak = Join-Path $outputPath ("_legacy_pak_" + (Get-Date -Format "yyyyMMdd_HHmmss") + "_" + $_.Name)
        Move-Item -LiteralPath $_.FullName -Destination $legacyPak
    }
    Copy-Item -LiteralPath $pakPath -Destination (Join-Path $outputPath "Paks\UnderpassTechDemo.pak") -Force
    Copy-Item -LiteralPath (Join-Path $repoRoot "build\underpass_techdemo\package_manifest.json") -Destination (Join-Path $outputPath "PACKAGE-MANIFEST.json") -Force
    Copy-Item -LiteralPath (Join-Path $repoRoot "openbor\runtime\OPENBOR-LICENSE.txt") -Destination $outputPath -Force
    Copy-Item -LiteralPath (Join-Path $repoRoot "openbor\runtime\OPENBOR-README.txt") -Destination $outputPath -Force
    @"
Fades of Fate 2.0 - Sunset Underpass Tech Demo

Run Launch_Black_Dave_Underpass_Demo.cmd. The launcher starts OpenBOR from this folder so ./Paks is resolved correctly.
Controls: arrows move, Ctrl attacks, Alt jumps, Enter starts.
Stage: four unique 640x360 panels with sunset parallax, drifting haze, grounded pixel detail, and rooted animated curb foliage.
"@ | Set-Content -LiteralPath (Join-Path $outputPath "READ_ME_FIRST.txt") -Encoding UTF8
    @"
@echo off
cd /d "%~dp0"
OpenBOR.exe
"@ | Set-Content -LiteralPath (Join-Path $outputPath "Launch_Black_Dave_Underpass_Demo.cmd") -Encoding ASCII

    $process = Start-Process -FilePath (Join-Path $outputPath "OpenBOR.exe") -ArgumentList ".\Paks\UnderpassTechDemo.pak" -WorkingDirectory $outputPath -PassThru
    Start-Sleep -Seconds 8
    if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        throw "Underpass free-walk executable exited during launch verification."
    }
    Stop-Process -Id $process.Id -Force

    $buildManifest = [ordered]@{
        product = "Fades of Fate 2.0 - Sunset Underpass Tech Demo"
        engine = "OpenBOR 4.0 Build 7949"
        source_commit = ((& git -C $repoRoot rev-parse HEAD).Trim())
        built_utc = ([DateTime]::UtcNow.ToString("o"))
        authored_black_dave_poses = 220
        package = "Paks/UnderpassTechDemo.pak"
        package_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $outputPath "Paks\UnderpassTechDemo.pak")).Hash
        executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $outputPath "OpenBOR.exe")).Hash
        launch_test = "pass-8-seconds"
        required_visual_gate = "Packaged forward/back traversal plus foliage-motion captures"
    }
    $buildManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $outputPath "BUILD-MANIFEST.json") -Encoding UTF8
} finally {
    Pop-Location
}

Write-Output "Underpass free-walk demo ready: $outputPath"
Write-Output "Launcher: $(Join-Path $outputPath 'Launch_Black_Dave_Underpass_Demo.cmd')"
