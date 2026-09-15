@echo off
setlocal
rem Per-process policy only; no administrator rights or global settings required.
powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0windows\install.ps1" %*
exit /b %ERRORLEVEL%
