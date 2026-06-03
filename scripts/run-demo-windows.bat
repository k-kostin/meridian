@echo off
setlocal

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo Python virtualenv not found: %cd%\.venv
    echo Create it first and install dependencies.
    exit /b 1
)

if "%DJANGO_DEBUG%"=="" set "DJANGO_DEBUG=0"
if "%DJANGO_ALLOWED_HOSTS%"=="" set "DJANGO_ALLOWED_HOSTS=*"
set "WAREHOUSE_DEMO_MODE=1"

.\.venv\Scripts\python.exe manage.py migrate
if errorlevel 1 exit /b 1

.\.venv\Scripts\python.exe manage.py seed_demo_data --reset
if errorlevel 1 exit /b 1

.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000 --insecure
