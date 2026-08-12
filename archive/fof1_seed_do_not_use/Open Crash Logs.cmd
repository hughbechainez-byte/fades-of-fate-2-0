@echo off
setlocal
if not exist "%~dp0logs" mkdir "%~dp0logs"
start "" explorer.exe "%~dp0logs"
