@echo off
set "OPENCODE_CONFIG_ROOT=%USERPROFILE%\\.config\\opencode"
set "OPENCODE_REPO_ROOT=%OPENCODE_REPO_ROOT%"
set "PYTHONPATH=%OPENCODE_CONFIG_ROOT%\\commands;%OPENCODE_CONFIG_ROOT%\\governance;%PATH%"
"%PYTHON%" -m governance.entrypoints.bootstrap_preflight_readonly
