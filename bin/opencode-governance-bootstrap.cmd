@echo off
setlocal EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
set "OPENCODE_CONFIG_ROOT=%OPENCODE_CONFIG_ROOT%"
if not defined OPENCODE_CONFIG_ROOT (
    for %%i in ("%SCRIPT_DIR%..") do set "OPENCODE_CONFIG_ROOT=%%~fi"
)

set "OPENCODE_REPO_ROOT=%OPENCODE_REPO_ROOT%"
if not defined OPENCODE_REPO_ROOT (
    if defined GITHUB_WORKSPACE (
        set "OPENCODE_REPO_ROOT=%GITHUB_WORKSPACE%"
    )
)

set "COMMANDS_HOME=%OPENCODE_CONFIG_ROOT%\commands"
set "OPENCODE_HOME=%OPENCODE_CONFIG_ROOT%"

set "PYTHON_EXE=%PYTHON%"
if not defined PYTHON_EXE (
    set "PYTHON_EXE=python"
)

set "PYTHONPATH=%COMMANDS_HOME%;%COMMANDS_HOME%\governance;!PYTHONPATH!"
set "OPENCODE_INTERNAL_BOOTSTRAP_CONFIG_ROOT=%OPENCODE_CONFIG_ROOT%"
set "OPENCODE_BOOTSTRAP_BINDING_PATH=%COMMANDS_HOME%\governance.paths.json"
if defined OPENCODE_REPO_ROOT (
    set "PYTHONPATH=%OPENCODE_REPO_ROOT%;%PYTHONPATH%"
)

set "OPENCODE_CONFIG_ROOT=%OPENCODE_CONFIG_ROOT%"
set "OPENCODE_REPO_ROOT=%OPENCODE_REPO_ROOT%"
set "COMMANDS_HOME=%COMMANDS_HOME%"
set "PYTHONPATH=%PYTHONPATH%"
if not defined OPENCODE_BOOTSTRAP_VERBOSE (
    set "OPENCODE_BOOTSTRAP_VERBOSE=0"
)
if not defined OPENCODE_BOOTSTRAP_OUTPUT (
    set "OPENCODE_BOOTSTRAP_OUTPUT=final"
)

rem --- Subcommand routing (python-binding-contract.v1 §4) ---
if "%~1"=="--session-reader" (
    shift
    "!PYTHON_EXE!" "%COMMANDS_HOME%\governance\entrypoints\session_reader.py" %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
if "%~1"=="--entrypoint" (
    shift
    set "MODULE=%~1"
    shift
    "!PYTHON_EXE!" -m !MODULE! %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
"!PYTHON_EXE!" -m governance.entrypoints.bootstrap_executor %*
set "WRAPPER_EXIT=%ERRORLEVEL%"
endlocal & exit /b %WRAPPER_EXIT%
