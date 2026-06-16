@echo off
setlocal

cd /d "%~dp0\..\.." || exit /b 1

set BUILD_ROOT=%LOCALAPPDATA%\MeridianBuild
set DIST_ROOT=%BUILD_ROOT%\dist
set WORK_ROOT=%BUILD_ROOT%\build
set SIDECAR_DIST=%DIST_ROOT%\warehouse-sidecar

if not exist .venv\Scripts\python.exe (
  echo ERROR: .venv not found. Create it first:
  echo   py -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install --upgrade pip
  exit /b 1
)

echo Installing runtime requirements...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%

echo Installing sidecar build requirements...
.venv\Scripts\python.exe -m pip install -r desktop\python_sidecar\requirements-build.txt
if errorlevel 1 exit /b %errorlevel%

echo Building Python sidecar...
.venv\Scripts\python.exe -m PyInstaller desktop\python_sidecar\warehouse-sidecar.spec --noconfirm --distpath "%DIST_ROOT%" --workpath "%WORK_ROOT%"
if errorlevel 1 exit /b %errorlevel%

if not exist "%SIDECAR_DIST%\warehouse-sidecar.exe" (
  echo ERROR: sidecar exe was not produced: %SIDECAR_DIST%\warehouse-sidecar.exe
  exit /b 1
)

echo Sidecar build complete.
echo Artifact: %SIDECAR_DIST%\warehouse-sidecar.exe
