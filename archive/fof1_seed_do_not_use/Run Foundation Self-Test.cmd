@echo off
setlocal
cd /d "%~dp0"
set "REPORT=%~dp0build\self_test_report.json"
if exist "%REPORT%" del /q "%REPORT%"
start /wait "" "%~dp0The Fades of Fate.exe" --self-test
set "TEST_EXIT=%ERRORLEVEL%"
if not "%TEST_EXIT%"=="0" (
  echo Self-test failed with exit code %TEST_EXIT%. Check logs\latest.log.
  pause
  exit /b %TEST_EXIT%
)
if not exist "%REPORT%" (
  echo Self-test report was not created. Check logs\latest.log.
  pause
  exit /b 1
)
powershell.exe -NoProfile -Command "$r = Get-Content -LiteralPath '%REPORT%' -Raw ^| ConvertFrom-Json; if ($r.status -ne 'pass') { exit 1 }"
if errorlevel 1 (
  echo Self-test report status is not PASS. Check logs\latest.log.
  pause
  exit /b 1
)
start "" notepad.exe "%REPORT%"
