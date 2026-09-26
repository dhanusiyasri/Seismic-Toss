@echo off
setlocal
cd /d "%~dp0backend"
if not exist "..\venv\Scripts\python.exe" (
  echo venv not found at ..\venv
  echo Create it with: python -m venv venv
  pause
  exit /b 1
)
call "..\venv\Scripts\activate.bat"
python -c "import sklearn; print('scikit-learn:', sklearn.__version__)"
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
