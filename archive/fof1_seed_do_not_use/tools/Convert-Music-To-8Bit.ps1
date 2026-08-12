#requires -Version 5.1
<#
.SYNOPSIS
Converts any FFmpeg-readable music file to a game-ready bitcrushed OGG.

.EXAMPLE
.\Convert-Music-To-8Bit.ps1 "C:\Music\fight song.mp3"

.EXAMPLE
.\Convert-Music-To-8Bit.ps1 "C:\Music\fight song.flac" `
    -OutputPath "C:\Game\assets\audio\boss_fight.ogg" -Force
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string] $InputPath,

    [Parameter(Position = 1)]
    [string] $OutputPath,

    [ValidateRange(8000, 48000)]
    [int] $SampleRate = 22050,

    [ValidateRange(2, 16)]
    [int] $CrusherBits = 8,

    [ValidateRange(1, 12)]
    [int] $SampleHold = 2,

    [ValidateRange(0, 86400)]
    [double] $StartSeconds = 0,

    [ValidateRange(0, 86400)]
    [double] $DurationSeconds = 0,

    [switch] $MelodyOnly,

    [switch] $InstallAsStageTrack,

    [switch] $InstallAsMenuTrack,

    [switch] $Force
)

$ErrorActionPreference = 'Stop'

try {
    $inputItem = Get-Item -LiteralPath $InputPath -ErrorAction Stop
    if ($inputItem.PSIsContainer) {
        throw "Input path is a directory, not a music file: $($inputItem.FullName)"
    }
    if ($InstallAsStageTrack -and $InstallAsMenuTrack) {
        throw 'Choose only one install target: stage track or menu track.'
    }

    $ffmpeg = Get-Command ffmpeg -CommandType Application -ErrorAction SilentlyContinue
    if ($null -eq $ffmpeg) {
        throw 'FFmpeg was not found. Install FFmpeg and make sure ffmpeg.exe is available on PATH.'
    }

    if ($InstallAsStageTrack -and [string]::IsNullOrWhiteSpace($OutputPath)) {
        $gameRoot = Split-Path -Parent $PSScriptRoot
        $OutputPath = Join-Path $gameRoot 'assets\audio\second_street_custom.ogg'
    }
    elseif ($InstallAsMenuTrack -and [string]::IsNullOrWhiteSpace($OutputPath)) {
        $gameRoot = Split-Path -Parent $PSScriptRoot
        $OutputPath = Join-Path $gameRoot 'assets\audio\menu_custom.ogg'
    }
    elseif ([string]::IsNullOrWhiteSpace($OutputPath)) {
        $stem = [IO.Path]::GetFileNameWithoutExtension($inputItem.Name)
        $OutputPath = Join-Path $inputItem.DirectoryName ($stem + '-8bit.ogg')
    }

    $outputFullPath = [IO.Path]::GetFullPath($OutputPath)
    if ([IO.Path]::GetExtension($outputFullPath) -ine '.ogg') {
        throw "Output must use the .ogg extension: $outputFullPath"
    }
    if ($outputFullPath -eq $inputItem.FullName) {
        throw 'Input and output paths must be different.'
    }
    if ((Test-Path -LiteralPath $outputFullPath) -and -not $Force) {
        throw "Output already exists. Add -Force to replace it: $outputFullPath"
    }

    $outputDirectory = Split-Path -Parent $outputFullPath
    if ([string]::IsNullOrWhiteSpace($outputDirectory)) {
        $outputDirectory = (Get-Location).Path
    }
    if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }

    if ($MelodyOnly) {
        $python = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
        if ($null -eq $python) {
            throw 'Melody-only conversion needs Python with NumPy available on PATH.'
        }
        $extractor = Join-Path $PSScriptRoot 'Extract-Chiptune-Melody.py'
        if (-not (Test-Path -LiteralPath $extractor -PathType Leaf)) {
            throw "Melody extractor not found: $extractor"
        }
        $melodyDuration = if ($DurationSeconds -gt 0) { $DurationSeconds } else { 90 }
        $ffmpegPath = (Get-Command ffmpeg -CommandType Application -ErrorAction Stop).Source
        $melodyMessages = @(& $python.Source $extractor $inputItem.FullName $outputFullPath --duration $melodyDuration --ffmpeg $ffmpegPath 2>&1)
        if ($LASTEXITCODE -ne 0) {
            throw (($melodyMessages | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine)
        }
        if ($InstallAsStageTrack -or $InstallAsMenuTrack) {
            $gameRoot = Split-Path -Parent $PSScriptRoot
            $gameplayPath = Join-Path $gameRoot 'data\gameplay.json'
            if (-not (Test-Path -LiteralPath $gameplayPath -PathType Leaf)) {
                throw "The editable game data file was not found: $gameplayPath"
            }
            $gameplay = Get-Content -LiteralPath $gameplayPath -Raw | ConvertFrom-Json
            $propertyName = if ($InstallAsMenuTrack) { 'menu_music' } else { 'stage_music' }
            $gameplay.audio | Add-Member -NotePropertyName $propertyName -NotePropertyValue ([IO.Path]::GetFileName($outputFullPath)) -Force
            $json = $gameplay | ConvertTo-Json -Depth 30
            [IO.File]::WriteAllText($gameplayPath, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
            $targetLabel = if ($InstallAsMenuTrack) { 'menu track' } else { 'Second Street track' }
            Write-Output "Installed as the $targetLabel. Restart the game to hear it."
        }
        Write-Output $outputFullPath
        return
    }

    $temporaryName = '{0}.partial.{1}.ogg' -f `
        [IO.Path]::GetFileNameWithoutExtension($outputFullPath), `
        [Guid]::NewGuid().ToString('N')
    $temporaryPath = Join-Path $outputDirectory $temporaryName
    $filterGraph = 'highpass=f=55,lowpass=f=6500,aresample=11025,' +
        ('acrusher=bits={0}:samples={1}:mix=1:mode=lin:aa=0.15,' -f $CrusherBits, $SampleHold) +
        ('aresample={0},alimiter=limit=0.92' -f $SampleRate)

    $arguments = @(
        '-hide_banner',
        '-loglevel', 'error',
        '-nostdin'
    )
    if ($StartSeconds -gt 0) {
        $arguments += @('-ss', $StartSeconds.ToString('0.###', [Globalization.CultureInfo]::InvariantCulture))
    }
    $arguments += @('-i', $inputItem.FullName)
    if ($DurationSeconds -gt 0) {
        $arguments += @('-t', $DurationSeconds.ToString('0.###', [Globalization.CultureInfo]::InvariantCulture))
    }
    $arguments += @(
        '-map_metadata', '-1',
        '-vn',
        '-ac', '2',
        '-af', $filterGraph,
        '-ar', $SampleRate.ToString(),
        '-c:a', 'libvorbis',
        '-q:a', '5',
        '-n',
        $temporaryPath
    )

    $ffmpegMessages = @(& $ffmpeg.Source @arguments 2>&1)
    $ffmpegExitCode = $LASTEXITCODE
    if ($ffmpegExitCode -ne 0) {
        $details = ($ffmpegMessages | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        if ([string]::IsNullOrWhiteSpace($details)) {
            $details = 'FFmpeg returned no diagnostic text.'
        }
        throw "FFmpeg could not convert '$($inputItem.FullName)' (exit $ffmpegExitCode).`n$details"
    }
    if (-not (Test-Path -LiteralPath $temporaryPath -PathType Leaf)) {
        throw 'FFmpeg reported success but did not create an output file.'
    }
    if ((Get-Item -LiteralPath $temporaryPath).Length -le 0) {
        throw 'FFmpeg created an empty output file.'
    }

    if (Test-Path -LiteralPath $outputFullPath) {
        Remove-Item -LiteralPath $outputFullPath -Force
    }
    Move-Item -LiteralPath $temporaryPath -Destination $outputFullPath
    if ($InstallAsStageTrack -or $InstallAsMenuTrack) {
        $gameRoot = Split-Path -Parent $PSScriptRoot
        $gameplayPath = Join-Path $gameRoot 'data\gameplay.json'
        if (-not (Test-Path -LiteralPath $gameplayPath -PathType Leaf)) {
            throw "The editable game data file was not found: $gameplayPath"
        }
        $gameplay = Get-Content -LiteralPath $gameplayPath -Raw | ConvertFrom-Json
        $propertyName = if ($InstallAsMenuTrack) { 'menu_music' } else { 'stage_music' }
        $gameplay.audio | Add-Member -NotePropertyName $propertyName -NotePropertyValue ([IO.Path]::GetFileName($outputFullPath)) -Force
        $json = $gameplay | ConvertTo-Json -Depth 30
        [IO.File]::WriteAllText($gameplayPath, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        $targetLabel = if ($InstallAsMenuTrack) { 'menu track' } else { 'Second Street track' }
        Write-Output "Installed as the $targetLabel. Restart the game to hear it."
    }
    Write-Output $outputFullPath
}
catch {
    if ($null -ne $temporaryPath -and (Test-Path -LiteralPath $temporaryPath)) {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
    Write-Error ("8-bit music conversion failed: " + $_.Exception.Message)
    exit 1
}
