@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import scipy, fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
echo Open http://127.0.0.1:8000 in your browser.
.venv\Scripts\python.exe -m uvicorn parkinglab.api:app --host 127.0.0.1 --port 8000
exit /b
:failed
echo Setup failed. Install Python 3.12 and check your network, then retry.
pause
