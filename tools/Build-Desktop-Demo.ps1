[CmdletBinding()]
param(
    [string]$OutputRoot = "dist\FadesOfFate2Demo",
    [switch]$SkipLaunchTest
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-PythonScript([string]$ScriptPath) {
    & python $ScriptPath
    if ($LASTEXITCODE -ne 0) {
        throw "Python build step failed: $ScriptPath (exit code $LASTEXITCODE)."
    }
}

if ([System.IO.Path]::IsPathFullyQualified($OutputRoot)) {
    $outputPath = [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    $outputPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputRoot))
}

$pakPath = Join-Path $repoRoot "build\openbor_black_dave\TheFadesOfFate2.pak"
$runtimePath = Join-Path $repoRoot "openbor\runtime\OpenBOR.exe"
$licensePath = Join-Path $repoRoot "openbor\runtime\OPENBOR-LICENSE.txt"
$readmePath = Join-Path $repoRoot "openbor\runtime\OPENBOR-README.txt"
$exePath = Join-Path $outputPath "FadesOfFate2.exe"
$pakOutputPath = Join-Path $outputPath "Paks\TheFadesOfFate2.pak"
$logPath = Join-Path $outputPath "Logs\OpenBorLog.txt"

Push-Location $repoRoot
try {
    Invoke-PythonScript "tools\Build-OpenBOR-Black-Dave.py"
    Invoke-PythonScript "tools\Build-OpenBOR-Package.py"
    Invoke-PythonScript "tools\Validate-OpenBOR-Black-Dave.py"

    if (-not (Test-Path $pakPath)) { throw "Expected PAK was not produced: $pakPath" }
    if (-not (Test-Path $runtimePath)) { throw "Pinned OpenBOR runtime was not found: $runtimePath" }

    New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $outputPath "Paks") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $outputPath "Logs") | Out-Null

    Copy-Item -LiteralPath $runtimePath -Destination $exePath -Force
    Copy-Item -LiteralPath $pakPath -Destination $pakOutputPath -Force
    if (Test-Path $licensePath) { Copy-Item -LiteralPath $licensePath -Destination (Join-Path $outputPath "OPENBOR-LICENSE.txt") -Force }
    if (Test-Path $readmePath) { Copy-Item -LiteralPath $readmePath -Destination (Join-Path $outputPath "OPENBOR-README.txt") -Force }

    $launchStatus = "not-run"
    if (-not $SkipLaunchTest) {
        $demoProcess = Start-Process -FilePath $exePath -WorkingDirectory $outputPath -PassThru
        try {
            Start-Sleep -Seconds 3
            if (-not (Get-Process -Id $demoProcess.Id -ErrorAction SilentlyContinue)) {
                throw "The packaged executable exited before launch verification completed."
            }
            $launchStatus = "pass"
        } finally {
            if (Get-Process -Id $demoProcess.Id -ErrorAction SilentlyContinue) {
                Stop-Process -Id $demoProcess.Id -Force
            }
        }
    }

    $manifest = [ordered]@{
        product = "Fades of Fate 2.0 desktop demo"
        executable = "FadesOfFate2.exe"
        package = "Paks/TheFadesOfFate2.pak"
        runtime = "OpenBOR 4.0 Build 7949"
        source_commit = ((& git -C $repoRoot rev-parse HEAD).Trim())
        built_utc = ([DateTime]::UtcNow.ToString("o"))
        executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $exePath).Hash
        package_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $pakOutputPath).Hash
        launch_test = $launchStatus
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $outputPath "BUILD-MANIFEST.json") -Encoding UTF8
} finally {
    Pop-Location
}

Write-Output "Desktop demo ready: $exePath"
Write-Output "Package: $pakOutputPath"
Write-Output "Manifest: $(Join-Path $outputPath 'BUILD-MANIFEST.json')"
