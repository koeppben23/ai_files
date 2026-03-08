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
if not defined PYTHON_EXE (
    set "PYTHON_EXE=C:/Python313/python.exe"
)
if not exist "!PYTHON_EXE!" (
    if exist "!BINDING_FILE!" (
        set /p PYTHON_EXE=<"!BINDING_FILE!"
    )
)

set "PYTHON_CMD="
if exist "!PYTHON_EXE!" (
    set "PYTHON_CMD=\"!PYTHON_EXE!\""
)

rem Degraded fallback is allowed only when no binding artifact exists.
if not defined PYTHON_CMD (
    if not exist "!BINDING_FILE!" (
        if defined pythonLocation (
            if exist "%pythonLocation%\python.exe" (
                set "PYTHON_CMD=\"%pythonLocation%\python.exe\""
            )
        )
        if not defined PYTHON_CMD (
            python -c "import sys" >nul 2>&1 && set "PYTHON_CMD=python"
        )
        if not defined PYTHON_CMD (
            py -3 -c "import sys" >nul 2>&1 && set "PYTHON_CMD=py -3"
        )
    )
)

if not defined PYTHON_CMD (
    echo FATAL: No valid Python interpreter found. >&2
    echo   Baked path: C:/Python313/python.exe >&2
    echo   PYTHON_BINDING: %SCRIPT_DIR%PYTHON_BINDING >&2
    echo   Re-run install.py to rebind. >&2
    exit /b 1
)
set "OPENCODE_PYTHON=!PYTHON_CMD!"

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
    !PYTHON_CMD! "%COMMANDS_HOME%\governance\entrypoints\session_reader.py" %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
if "%~1"=="--ticket-persist" (
    shift
    !PYTHON_CMD! -m governance.entrypoints.phase4_intake_persist %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
if "%~1"=="--plan-persist" (
    shift
    !PYTHON_CMD! -m governance.entrypoints.phase5_plan_record_persist %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
if "%~1"=="--entrypoint" (
    shift
    rem Compatibility path (deprecated after one versioned bundle release)
    set "MODULE=%~1"
    shift
    !PYTHON_CMD! -m !MODULE! %*
    set "WRAPPER_EXIT=%ERRORLEVEL%"
    endlocal & exit /b %WRAPPER_EXIT%
)
!PYTHON_CMD! -m governance.entrypoints.bootstrap_executor %*
set "WRAPPER_EXIT=%ERRORLEVEL%"
endlocal & exit /b %WRAPPER_EXIT%
