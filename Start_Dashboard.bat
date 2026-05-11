@echo off
setlocal
REM ──────────────────────────────────────────────────────────────
REM  Gap-Time Dashboard launcher (LAN-shareable)
REM
REM  After this starts, share ONE of these URLs with coworkers:
REM    • You (this PC):     http://localhost:8501
REM    • Same network:      http://%COMPUTERNAME%:8501
REM
REM  The console window must stay open. Close it to stop the dashboard.
REM ──────────────────────────────────────────────────────────────

cd /d "%~dp0"

echo.
echo === Gap-Time Dashboard ===
echo Working dir: %CD%
echo.

REM 1) Find Python
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo         Install Python 3.10+ from https://www.python.org/downloads/
    echo         and check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

REM 2) Install / upgrade dependencies (only does real work first time)
echo Installing dependencies (first run can take a minute)...
python -m pip install --quiet --disable-pip-version-check streamlit pandas openpyxl
if errorlevel 1 (
    echo [ERROR] pip install failed. Re-run from a regular Command Prompt
    echo         to see the full error message.
    pause
    exit /b 1
)

REM 3) Show the URLs the user can share
echo.
echo Starting server...
echo   Local:    http://localhost:8501
echo   Network:  http://%COMPUTERNAME%:8501
echo.
echo Opening Chrome in 4 seconds. Leave this window open.
echo.

REM 4) Open Chrome shortly after launch (give the server time to bind)
start "" /b cmd /c "timeout /t 4 /nobreak >nul && start chrome http://localhost:8501"

REM 5) Run Streamlit in the foreground so you can SEE any errors.
REM    --server.address 0.0.0.0 makes it reachable from other PCs on your LAN.
python -m streamlit run dashboard.py ^
    --server.address 0.0.0.0 ^
    --server.port 8501 ^
    --server.headless true ^
    --browser.gatherUsageStats false

echo.
echo Server stopped.
pause
endlocal
