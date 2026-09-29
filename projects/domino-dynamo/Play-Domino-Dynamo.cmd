@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\red.ps1" play-local
if errorlevel 1 pause
