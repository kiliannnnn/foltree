@echo off
REM Launch Foltree. Creates the virtualenv and installs dependencies the first
REM time, then goes straight to the app on every later run.
REM
REM   run.bat                 -> opens the app
REM   run.bat scan . -f md    -> passes arguments through to the CLI
setlocal
cd /d "%~dp0"

REM Prefer the "py" launcher: a bare "python" is often the Microsoft Store
REM stub, which exists on PATH but only opens the Store.
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python 3 not found. Install it from https://python.org and tick "Add to PATH".
    pause
    exit /b 1
)

if not exist ".venv" (
    echo First run: creating virtual environment in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Could not create the virtual environment.
        pause
        exit /b 1
    )
)

REM Reinstall only when requirements.txt is newer than the stamp file.
set STAMP=.venv\.requirements-stamp
if not exist "%STAMP%" goto install
for /f %%i in ('dir /b /o:d "%STAMP%" requirements.txt 2^>nul') do set NEWEST=%%i
if /i "%NEWEST%"=="requirements.txt" goto install
goto run

:install
echo Installing dependencies ...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
echo. > "%STAMP%"

:run
if "%~1"=="" (
    REM pythonw keeps the console window from hanging around behind the app.
    start "" .venv\Scripts\pythonw.exe -m foltree
) else (
    .venv\Scripts\python.exe -m foltree %*
)
endlocal
