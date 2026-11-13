@echo off
setlocal
cd /d "%~dp0"
if not exist .env (
 echo Copy .env.example to .env and configure it first.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
goto end
:fail
echo Migration failed.
:end
pause
