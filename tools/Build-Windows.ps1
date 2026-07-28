#requires -Version 5.1
[CmdletBinding()]
param(
    [switch] $SkipTests,
    [switch] $SkipDesktopInstall,
    [switch] $VisualReviewApproved
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Virtual environment is missing: $python"
}

Push-Location $projectRoot
try {
    $savedVideoDriver = $env:SDL_VIDEODRIVER
    $savedAudioDriver = $env:SDL_AUDIODRIVER
    $env:SDL_VIDEODRIVER = 'dummy'
    $env:SDL_AUDIODRIVER = 'dummy'
    if (-not $SkipTests) {
        & $python -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed.' }
        & $python -m src.main --self-test
        if ($LASTEXITCODE -ne 0) { throw 'Source foundation self-test failed.' }
    }

    # Location-lock QA is a packaging prerequisite, including for an explicit
    # -SkipTests rebuild.  It produces the five-checkpoint normal/overlay
    # sheets and rejects manifest, geometry, or source metadata drift.
    $sourceSceneryReport = Join-Path $projectRoot 'build\chapter1_location_sources_report.json'
    $sourceRouteWorldlockScreenshot = Join-Path $projectRoot 'build\route_worldlocked_qa.png'
    $projectionOutputDir = Join-Path $projectRoot 'build\projection-calibration'
    $projectionReport = Join-Path $projectionOutputDir 'projection_calibration_report.json'
    foreach ($staleArtifact in @(
        $sourceSceneryReport,
        $sourceRouteWorldlockScreenshot,
        $projectionReport
    )) {
        if (Test-Path -LiteralPath $staleArtifact) {
            Remove-Item -LiteralPath $staleArtifact -Force
        }
    }
    $projectionTool = Join-Path $projectRoot 'tools\Render-Projection-Calibration.py'
    if (-not (Test-Path -LiteralPath $projectionTool -PathType Leaf)) {
        throw "Projection calibration tool is missing: $projectionTool"
    }
    & $python $projectionTool --project-root $projectRoot --output-dir $projectionOutputDir
    if ($LASTEXITCODE -ne 0) { throw 'Projection calibration QA failed.' }
    if (-not (Test-Path -LiteralPath $projectionReport -PathType Leaf)) {
        throw "Expected projection calibration report was not produced: $projectionReport"
    }
    $sceneryQaArgs = @(
        (Join-Path $projectRoot 'tools\Render-Route-Scenery-QA.py')
    )
    if ($VisualReviewApproved) {
        $sceneryQaArgs += '--visual-review-approved'
    }
    & $python @sceneryQaArgs
    if ($LASTEXITCODE -ne 0) { throw 'Chapter 1 scenery QA failed.' }
    if (-not (Test-Path -LiteralPath $sourceSceneryReport -PathType Leaf)) {
        throw "Expected scenery QA report was not produced: $sourceSceneryReport"
    }
    if (-not (Test-Path -LiteralPath $sourceRouteWorldlockScreenshot -PathType Leaf)) {
        throw "Expected route worldlock screenshot was not produced: $sourceRouteWorldlockScreenshot"
    }
    $sourceSceneryPayload = Get-Content -LiteralPath $sourceSceneryReport -Raw | ConvertFrom-Json
    if (-not $sourceSceneryPayload.passed) {
        throw "Source scenery report did not pass: $sourceSceneryReport"
    }
    $sourceAssetInventoryHash = [string] $sourceSceneryPayload.automated_validation.asset_inventory_sha256
    if ([string]::IsNullOrWhiteSpace($sourceAssetInventoryHash)) {
        throw "Source scenery report did not contain an asset inventory hash: $sourceSceneryReport"
    }
    $sourceValidationReport = Join-Path $projectRoot 'build\chapter1_validation_build.json'
    & $python (Join-Path $projectRoot 'tools\validate_chapter1.py') --output $sourceValidationReport
    if ($LASTEXITCODE -ne 0) { throw 'Chapter 1 validation or performance gate failed.' }
    $env:SDL_VIDEODRIVER = $savedVideoDriver
    $env:SDL_AUDIODRIVER = $savedAudioDriver

    $distRoot = Join-Path $projectRoot 'dist'
    $workRoot = Join-Path $projectRoot 'build\pyinstaller'
    $specRoot = Join-Path $projectRoot 'build'
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --noupx `
        --name 'The Fades of Fate' `
        --distpath $distRoot `
        --workpath $workRoot `
        --specpath $specRoot `
        --paths $projectRoot `
        --hidden-import pygame._sdl2.controller `
        --add-data "$(Join-Path $projectRoot 'assets');assets" `
        --add-data "$(Join-Path $projectRoot 'data');data" `
        (Join-Path $projectRoot 'src\main.py')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

    $packageDir = Join-Path $distRoot 'The Fades of Fate'
    $exe = Join-Path $packageDir 'The Fades of Fate.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "Packaged executable was not created: $exe"
    }
    $packageExeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $exe).Hash

    Copy-Item -LiteralPath (Join-Path $projectRoot 'data') -Destination $packageDir -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot 'assets') -Destination $packageDir -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot 'tools') -Destination $packageDir -Recurse -Force
    foreach ($file in @(
        'README.md',
        'ToDoList.md',
        'SECOND_STREET_AND_ANIMATION_KNOWLEDGE_BASE.md',
        'THIRD_PARTY_NOTICES.txt',
        'Convert Music to 8-Bit.cmd',
        'Run Foundation Self-Test.cmd',
        'Open Crash Logs.cmd'
    )) {
        Copy-Item -LiteralPath (Join-Path $projectRoot $file) -Destination $packageDir -Force
    }
    New-Item -ItemType Directory -Path (Join-Path $packageDir 'logs') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $packageDir 'build') -Force | Out-Null

    $packageLocationReport = Join-Path $packageDir 'build\chapter1_location_package_validation.json'
    & $python (Join-Path $projectRoot 'tools\validate_chapter1.py') `
        --location-only `
        --project-root $packageDir `
        --output $packageLocationReport
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged location assets failed validation: $packageLocationReport"
    }
    $packageLocationPayload = Get-Content -LiteralPath $packageLocationReport -Raw | ConvertFrom-Json
    $packageAssetInventoryHash = [string] $packageLocationPayload.asset_inventory_sha256
    if ($packageAssetInventoryHash -ne $sourceAssetInventoryHash) {
        throw "Packaged location asset inventory mismatch. Source=$sourceAssetInventoryHash Package=$packageAssetInventoryHash"
    }

    $testProcess = Start-Process -FilePath $exe -ArgumentList '--self-test' -WorkingDirectory $packageDir -WindowStyle Hidden -Wait -PassThru
    if ($testProcess.ExitCode -ne 0) {
        throw "Packaged self-test failed with exit code $($testProcess.ExitCode)."
    }
    $reportPath = Join-Path $packageDir 'build\self_test_report.json'
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($report.status -ne 'pass') {
        throw "Packaged self-test report did not pass: $reportPath"
    }
    $requiredSceneryChecks = @(
        # Level 1 is the foundation self-test's live gameplay frame; later
        # routes have dedicated background-only checks after campaign travel.
        'gameplay_render',
        'level_2_background_render',
        'level_3_background_render',
        'level_four_runtime_snapshot',
        'awaken_refined_sunset_render'
    )
    $passedSelfTestChecks = @(
        $report.checks |
            Where-Object { $_.status -eq 'pass' } |
            ForEach-Object { [string] $_.name }
    )
    foreach ($requiredCheck in $requiredSceneryChecks) {
        if ($passedSelfTestChecks -notcontains $requiredCheck) {
            throw "Packaged self-test did not exercise required location scenery check: $requiredCheck"
        }
    }

    if (-not $SkipDesktopInstall) {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $desktopFull = [IO.Path]::GetFullPath($desktop).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        $target = [IO.Path]::GetFullPath((Join-Path $desktop 'The Fades of Fate Demo'))
        if (-not $target.StartsWith($desktopFull, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to replace a target outside Desktop: $target"
        }
        if ((Split-Path -Leaf $target) -ne 'The Fades of Fate Demo') {
            throw "Unexpected Desktop target name: $target"
        }
        # Keep the stable Desktop folder in place. Explorer or a freshly
        # closed game process may retain the directory handle briefly; a
        # recursive replacement can then delete the good package and fail
        # before its replacement arrives. Updating each validated package
        # child in place is atomic enough for this development deliverable and
        # preserves a launchable build if an unrelated folder handle is held.
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        foreach ($packageItem in @(Get-ChildItem -LiteralPath $packageDir -Force)) {
            Copy-Item -LiteralPath $packageItem.FullName -Destination $target -Recurse -Force
        }
        $desktopExe = Join-Path $target 'The Fades of Fate.exe'
        if (-not (Test-Path -LiteralPath $desktopExe -PathType Leaf)) {
            throw "Desktop copy did not contain the executable: $desktopExe"
        }
        $desktopExeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $desktopExe).Hash
        if ($desktopExeHash -ne $packageExeHash) {
            throw "Installed executable hash mismatch. Package=$packageExeHash Installed=$desktopExeHash"
        }

        $desktopLocationReport = Join-Path $target 'build\chapter1_location_installed_validation.json'
        & $python (Join-Path $projectRoot 'tools\validate_chapter1.py') `
            --location-only `
            --project-root $target `
            --output $desktopLocationReport
        if ($LASTEXITCODE -ne 0) {
            throw "Installed location assets failed validation: $desktopLocationReport"
        }
        $desktopLocationPayload = Get-Content -LiteralPath $desktopLocationReport -Raw | ConvertFrom-Json
        $desktopAssetInventoryHash = [string] $desktopLocationPayload.asset_inventory_sha256
        if ($desktopAssetInventoryHash -ne $sourceAssetInventoryHash) {
            throw "Installed location asset inventory mismatch. Source=$sourceAssetInventoryHash Installed=$desktopAssetInventoryHash"
        }

        # Exercise the installed copy as a separate package boundary. This
        # catches incomplete in-place asset copies even when the staging build
        # passed moments earlier.
        $desktopTestProcess = Start-Process -FilePath $desktopExe -ArgumentList '--self-test' -WorkingDirectory $target -WindowStyle Hidden -Wait -PassThru
        if ($desktopTestProcess.ExitCode -ne 0) {
            throw "Desktop self-test failed with exit code $($desktopTestProcess.ExitCode)."
        }
        $desktopReportPath = Join-Path $target 'build\self_test_report.json'
        $desktopReport = Get-Content -LiteralPath $desktopReportPath -Raw | ConvertFrom-Json
        if ($desktopReport.status -ne 'pass') {
            throw "Desktop self-test report did not pass: $desktopReportPath"
        }
        $passedDesktopChecks = @(
            $desktopReport.checks |
                Where-Object { $_.status -eq 'pass' } |
                ForEach-Object { [string] $_.name }
        )
        foreach ($requiredCheck in $requiredSceneryChecks) {
            if ($passedDesktopChecks -notcontains $requiredCheck) {
                throw "Desktop self-test did not exercise required location scenery check: $requiredCheck"
            }
        }

        $shortcutPath = Join-Path $desktop 'The Fades of Fate.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $target 'The Fades of Fate.exe'
        $shortcut.WorkingDirectory = $target
        $shortcut.Description = 'Launch The Fades of Fate local co-op foundation demo'
        $shortcut.Save()
        Write-Output "DESKTOP_GAME=$target"
        Write-Output "DESKTOP_SHORTCUT=$shortcutPath"
        Write-Output "DESKTOP_SELF_TEST=$desktopReportPath"
        Write-Output "DESKTOP_LOCATION_VALIDATION=$desktopLocationReport"
        Write-Output "DESKTOP_EXE_SHA256=$desktopExeHash"
    }

    Write-Output "PACKAGE=$packageDir"
    Write-Output "SELF_TEST=$reportPath"
    Write-Output "PACKAGE_LOCATION_VALIDATION=$packageLocationReport"
    Write-Output "PACKAGE_EXE_SHA256=$packageExeHash"
    Write-Output "SOURCE_SCENERY_REPORT=$sourceSceneryReport"
    Write-Output "SOURCE_WORLDLOCK_CAPTURE=$sourceRouteWorldlockScreenshot"
    Write-Output "SOURCE_ASSET_INVENTORY_SHA256=$sourceAssetInventoryHash"
    Write-Output "PROJECTION_CALIBRATION=$projectionReport"
    Write-Output "SOURCE_CHAPTER1_VALIDATION=$sourceValidationReport"
}
finally {
    if (Get-Variable -Name savedVideoDriver -ErrorAction SilentlyContinue) {
        $env:SDL_VIDEODRIVER = $savedVideoDriver
    }
    if (Get-Variable -Name savedAudioDriver -ErrorAction SilentlyContinue) {
        $env:SDL_AUDIODRIVER = $savedAudioDriver
    }
    Pop-Location
}
