@echo off
setlocal
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

set "COMMANDS_HOME=%COMMANDS_HOME%"
if not defined COMMANDS_HOME (
    set "COMMANDS_HOME=%OPENCODE_CONFIG_ROOT%\commands"
)

set "PYTHONPATH=%COMMANDS_HOME%;%COMMANDS_HOME%\governance;%PYTHONPATH%"
if defined OPENCODE_REPO_ROOT (
    set "PYTHONPATH=%OPENCODE_REPO_ROOT%;%PYTHONPATH%"
) else (
    for /f "delims=" %%i in ('git rev-parse --show-toplevel 2^>nul') do set "PYTHONPATH=%%i;%PYTHONPATH%"
)

set "PYTHON_EXE=%PYTHON%"
if not defined PYTHON_EXE (
    set "PYTHON_EXE=python"
)

set "PYTHON_FROM_BINDING="
if exist "%COMMANDS_HOME%\governance.paths.json" (
    where powershell >nul 2>nul
    if %errorlevel%==0 (
        for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$p='%COMMANDS_HOME%\governance.paths.json';try{$j=Get-Content -Raw -Path $p|ConvertFrom-Json;$j.paths.pythonCommand}catch{}"`) do set "PYTHON_FROM_BINDING=%%i"
    ) else (
        for /f "usebackq delims=" %%i in (`python -c "import json,os; p=os.path.join(r'%COMMANDS_HOME%','governance.paths.json');
try:
    data=json.load(open(p, 'r', encoding='utf-8'))
    print(data.get('paths',{}).get('pythonCommand',''))
except Exception:
    pass" 2^>nul`) do set "PYTHON_FROM_BINDING=%%i"
    )
)
if defined PYTHON_FROM_BINDING (
    if exist "%PYTHON_FROM_BINDING%" (
        set "PYTHON_EXE=%PYTHON_FROM_BINDING%"
        set "PYTHON_ARGS="
    ) else (
        for /f "tokens=1,*" %%a in ("%PYTHON_FROM_BINDING%") do (
            set "PYTHON_EXE=%%~a"
            set "PYTHON_ARGS=%%~b"
        )
    )
)

set "OPENCODE_CONFIG_ROOT=%OPENCODE_CONFIG_ROOT%"
set "OPENCODE_REPO_ROOT=%OPENCODE_REPO_ROOT%"
set "COMMANDS_HOME=%COMMANDS_HOME%"
set "PYTHONPATH=%PYTHONPATH%"

"%PYTHON_EXE%" %PYTHON_ARGS% -m cli.bootstrap %*
endlocal
