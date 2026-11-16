@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Run setup.cmd first.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m app.check %*
set "check_result=%errorlevel%"
pause
exit /b %check_result%
