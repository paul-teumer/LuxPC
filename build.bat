@echo off
rem Erzeugt dist\LuxPC.exe: eine einzelne Datei, die ohne Python oder sonstige Installation läuft.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
pause
