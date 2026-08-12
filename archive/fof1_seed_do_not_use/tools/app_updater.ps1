param(
    [Parameter(Mandatory = $true)] [string] $ManifestPath,
    [Parameter(Mandatory = $true)] [string] $TargetDirectory,
    [Parameter(Mandatory = $true)] [int] $ParentPid,
    [Parameter(Mandatory = $true)] [string] $ExecutableName
)

$ErrorActionPreference = 'Stop'
$handoffRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$downloadRoot = Join-Path ([IO.Path]::GetTempPath()) ('fades-of-fate-package-' + [guid]::NewGuid().ToString('N'))
$archivePath = Join-Path $downloadRoot 'package.zip'
$extractRoot = Join-Path $downloadRoot 'package'
$backupDirectory = "$TargetDirectory.update-backup"

function Fail([string] $Message) {
    throw "The Fades of Fate update failed: $Message"
}

try {
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ($manifest.schema_version -ne 1 -or $manifest.product -ne 'The Fades of Fate' -or $manifest.platform -ne 'windows-x64') {
        Fail 'the application manifest is not valid for this Windows build'
    }
    $url = [string]$manifest.package_url
    $uri = [Uri]$url
    if ($uri.Scheme -ne 'https' -or $uri.Host -notin @('github.com')) {
        Fail 'the package URL is not a trusted HTTPS GitHub URL'
    }
    $expectedHash = ([string]$manifest.package_sha256).ToLowerInvariant()
    if ($expectedHash -notmatch '^[0-9a-f]{64}$') {
        Fail 'the package SHA-256 is invalid'
    }
    $expectedSize = [int64]$manifest.package_size
    if ($expectedSize -le 0) {
        Fail 'the package size is invalid'
    }

    New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
    Invoke-WebRequest -Uri $url -OutFile $archivePath -UseBasicParsing
    $downloaded = Get-Item -LiteralPath $archivePath
    if ($downloaded.Length -ne $expectedSize) {
        Fail "download size mismatch: expected $expectedSize, got $($downloaded.Length)"
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        Fail "download hash mismatch: expected $expectedHash, got $actualHash"
    }

    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
    $newExecutable = Join-Path $extractRoot $ExecutableName
    if (-not (Test-Path -LiteralPath $newExecutable -PathType Leaf)) {
        Fail "verified package does not contain $ExecutableName"
    }

    # The game owns files under TargetDirectory until its process exits. The
    # helper itself lives in TEMP, so the directory can be swapped safely.
    $deadline = (Get-Date).AddSeconds(90)
    while ($true) {
        $parent = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
        if ($null -eq $parent) { break }
        if ((Get-Date) -ge $deadline) { Fail 'the running game did not exit in time' }
        Start-Sleep -Milliseconds 250
    }

    if (Test-Path -LiteralPath $backupDirectory) {
        Remove-Item -LiteralPath $backupDirectory -Recurse -Force
    }
    Move-Item -LiteralPath $TargetDirectory -Destination $backupDirectory -Force
    try {
        Move-Item -LiteralPath $extractRoot -Destination $TargetDirectory -Force
    }
    catch {
        Move-Item -LiteralPath $backupDirectory -Destination $TargetDirectory -Force
        throw
    }
    Remove-Item -LiteralPath $backupDirectory -Recurse -Force
    Start-Process -FilePath (Join-Path $TargetDirectory $ExecutableName) -WorkingDirectory $TargetDirectory
}
catch {
    $errorPath = Join-Path $handoffRoot 'update-error.txt'
    $_ | Out-String | Set-Content -LiteralPath $errorPath -Encoding UTF8
    exit 1
}
finally {
    Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ManifestPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $handoffRoot -Recurse -Force -ErrorAction SilentlyContinue
}
