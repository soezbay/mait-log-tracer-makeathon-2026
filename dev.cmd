@echo off
rem Start backend + frontend together. Works from cmd and PowerShell: .\dev
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1" %*
