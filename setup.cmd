@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist .env copy .env.example .env >nul
echo Edit .env: KEITARO_URL, KEITARO_API_KEY and APP_PASSWORD.
echo Then run start.cmd.
pause
exit /b 0
:fail
echo Setup failed. See the error above.
pause
exit /b 1
