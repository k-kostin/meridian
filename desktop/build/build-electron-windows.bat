@echo off
setlocal

cd /d "%~dp0\..\.." || exit /b 1

set BUILD_ROOT=%LOCALAPPDATA%\MeridianBuild
set SIDECAR_DIST=%BUILD_ROOT%\dist\warehouse-sidecar
set ELECTRON_BACKEND=desktop\electron_shell\resources\backend

if not exist "%SIDECAR_DIST%\warehouse-sidecar.exe" (
  echo Sidecar artifact missing. Running sidecar build first...
  call desktop\build\build-sidecar-windows.bat
  if errorlevel 1 exit /b %errorlevel%
)

if not exist "%SIDECAR_DIST%\warehouse-sidecar.exe" (
  echo ERROR: sidecar exe still missing after build.
  exit /b 1
)

echo Refreshing Electron backend resources...
if exist "%ELECTRON_BACKEND%" rmdir /s /q "%ELECTRON_BACKEND%"
if errorlevel 1 exit /b %errorlevel%
if exist "%ELECTRON_BACKEND%" (
  echo ERROR: failed to remove existing backend resources: %ELECTRON_BACKEND%
  exit /b 1
)
mkdir "%ELECTRON_BACKEND%"
if errorlevel 1 exit /b %errorlevel%
xcopy "%SIDECAR_DIST%\*" "%ELECTRON_BACKEND%\" /E /I /Y
if errorlevel 1 exit /b %errorlevel%

cd desktop\electron_shell

echo Installing Electron dependencies...
call npm install
if errorlevel 1 exit /b %errorlevel%

echo Checking Electron packaging contract...
call npm run check:contract
if errorlevel 1 exit /b %errorlevel%

echo Building Windows NSIS installer...
call npm run dist:win
if errorlevel 1 exit /b %errorlevel%

echo Electron Windows build complete.
echo Artifacts are in desktop\electron_shell\dist
