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
set "PYTHONPATH=%COMMANDS_HOME%;%COMMANDS_HOME%\governance;!PYTHONPATH!"
set "OPENCODE_INTERNAL_BOOTSTRAP_CONFIG_ROOT=%OPENCODE_CONFIG_ROOT%"
set "OPENCODE_BOOTSTRAP_BINDING_PATH=%COMMANDS_HOME%\governance.paths.json"
if defined OPENCODE_REPO_ROOT (
    set "PYTHONPATH=%OPENCODE_REPO_ROOT%;%PYTHONPATH%"
)

rem --- Python resolution cascade (python-binding-contract.v1 §3) ---
set "BINDING_FILE=%SCRIPT_DIR%PYTHON_BINDING"
set "PYTHON_EXE=%OPENCODE_PYTHON%"
if defined PYTHON_EXE if not exist "!PYTHON_EXE!" (
    set "PYTHON_EXE="
)
if not defined PYTHON_EXE (
    if exist "!BINDING_FILE!" (
        set /p PYTHON_EXE=<"!BINDING_FILE!"
    )
)
if not exist "!PYTHON_EXE!" (
    echo FATAL: No valid Python interpreter found. >&2
    echo   Baked path: %OPENCODE_PYTHON% >&2
    echo   PYTHON_BINDING: %SCRIPT_DIR%PYTHON_BINDING >&2
    echo   Re-run install.py to rebind. >&2
    exit /b 1
)
set "OPENCODE_PYTHON=!PYTHON_EXE!"

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
if "%~1"=="--ticket-persist" (
    shift
    "!PYTHON_EXE!" -m governance.entrypoints.phase4_intake_persist %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
if "%~1"=="--plan-persist" (
    shift
    "!PYTHON_EXE!" -m governance.entrypoints.phase5_plan_record_persist %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
if "%~1"=="--review-decision-persist" (
    shift
    "!PYTHON_EXE!" -m governance.entrypoints.review_decision_persist %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
if "%~1"=="--implement-start" (
    shift
    "!PYTHON_EXE!" -m governance.entrypoints.implement_start %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
if "%~1"=="--implementation-decision-persist" (
    shift
    "!PYTHON_EXE!" -m governance.entrypoints.implementation_decision_persist %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
if "%~1"=="--human-approval-persist" (
    shift
    "!PYTHON_EXE!" -m governance.entrypoints.human_approval_persist %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
"!PYTHON_EXE!" -m governance.entrypoints.bootstrap_executor %*
set "WRAPPER_EXIT=%ERRORLEVEL%"
endlocal & exit /b %WRAPPER_EXIT%
