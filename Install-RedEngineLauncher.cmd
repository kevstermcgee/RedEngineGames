@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-RedEngineLauncher.ps1" -Launch
if errorlevel 1 pause

