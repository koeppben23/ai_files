@echo off
set "OPENCODE_CONFIG_ROOT=%USERPROFILE%\\.config\\opencode"
set "OPENCODE_REPO_ROOT=%OPENCODE_REPO_ROOT%"
set "PYTHONPATH=%OPENCODE_CONFIG_ROOT%\\commands;%OPENCODE_CONFIG_ROOT%\\governance;%PATH%"
set "PYTHON=python"
REM Auto-detect repo root from git or OPENCODE_REPO_ROOT
if defined OPENCODE_REPO_ROOT (
    set "PYTHONPATH=%OPENCODE_REPO_ROOT%;%PYTHONPATH%"
) else (
    for /f "delims=" %%i in ('git rev-parse --show-toplevel 2^>nul') do set "PYTHONPATH=%%i;%PYTHONPATH%"
)

"%PYTHON%" -m cli.bootstrap %*
