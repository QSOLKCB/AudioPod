@echo off
setlocal
cd /d "%~dp0"
uv run --offline --locked audiopod gui
if errorlevel 1 (
  echo.
  echo AudioPod could not start. See docs\INSTALLATION.md for setup instructions.
  pause
  exit /b 1
)
