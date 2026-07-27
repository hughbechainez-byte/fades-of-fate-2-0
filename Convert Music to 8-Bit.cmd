@echo off
setlocal
if "%~1"=="" (
  echo Drag any music file onto this shortcut to convert and install it.
  echo The game will use the converted track on Second Street after restart.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Convert-Music-To-8Bit.ps1" -InputPath "%~1" -InstallAsStageTrack -Force
if errorlevel 1 (
  echo.
  echo Conversion failed. The message above explains why.
  pause
  exit /b 1
)
echo.
echo Music installed. Restart The Fades of Fate to hear it.
pause
