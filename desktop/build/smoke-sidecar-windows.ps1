param(
  [string]$SidecarPath = "$env:LOCALAPPDATA\MeridianBuild\dist\warehouse-sidecar\warehouse-sidecar.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path "$PSScriptRoot\..\.."
$SmokeScript = Join-Path $ProjectRoot "scripts\smoke_sidecar.py"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
  throw "Python venv not found: $Python"
}

if (!(Test-Path $SmokeScript)) {
  throw "Smoke runner not found: $SmokeScript"
}

if (!(Test-Path $SidecarPath)) {
  throw "Sidecar executable not found: $SidecarPath"
}

& $Python $SmokeScript --command $SidecarPath
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
