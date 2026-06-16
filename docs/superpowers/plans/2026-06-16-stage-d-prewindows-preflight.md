# Stage D Pre-Windows Preflight Implementation Plan

> **For agentic workers:** Use the repo implementation-plan workflow to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the maximum number of Stage D packaging-readiness questions on macOS before manual real Excel validation and before running the app on a real Windows machine.

**Architecture:** Keep Django as the only business-logic runtime and keep Electron as orchestration only. Add deterministic build scripts, preflight validators, smoke scripts, and handoff checklists so the later Windows session becomes a mechanical verification pass rather than exploratory debugging.

**Tech Stack:** Django 6, SQLite, Waitress sidecar, PyInstaller onedir, Electron 31, electron-builder NSIS, Node.js scripts, Python stdlib smoke tests, GitHub PR/Gemini review workflow.

---

## Scope

This plan intentionally avoids two manual gates:

- Manual validation of real client Excel workbooks.
- Real Windows NSIS installer execution on a Windows machine.

Everything else that can be prepared from macOS should be made explicit, scripted, documented, and verified.

## File Structure

Create or modify these files:

- Create: `desktop/build/build-sidecar-windows.bat`
  - Windows-only sidecar build script using the project `.venv`, `desktop/python_sidecar/requirements-build.txt`, and PyInstaller onedir output under `%LOCALAPPDATA%\MeridianBuild`.
- Create: `desktop/build/build-electron-windows.bat`
  - Windows-only end-to-end packaging script that validates sidecar output, stages `resources/backend`, installs Electron dependencies, and runs `npm run dist:win`.
- Create: `desktop/build/smoke-sidecar-windows.ps1`
  - Windows smoke script that starts built `warehouse-sidecar.exe` with a temp data-dir and checks `/healthz/`, `/`, and one Excel export.
- Create: `desktop/electron_shell/scripts/check-packaging-contract.js`
  - Cross-platform static packaging contract validator for Electron config, `src/main.js`, resource paths, dynamic port, shutdown token, and unsafe fixed-port regressions.
- Create: `scripts/smoke_sidecar.py`
  - Cross-platform Python smoke runner for source or packaged sidecar. Uses only stdlib: starts a process, waits for `/healthz/`, checks HTML and Excel endpoints, and shuts down with the runtime token when available.
- Create: `docs/audits/2026-06-16-stage-d-prewindows-gate.md`
  - Public-safe audit note recording what was verified on macOS and what remains for Windows/manual Excel.
- Modify: `desktop/electron_shell/package.json`
  - Add `check:contract` script.
- Modify: `desktop/electron_shell/README.md`
  - Add commands for preflight and Windows scripts.
- Modify: `docs/DESKTOP_APP.md`
  - Align Stage D flow with the new scripts and smoke contract.
- Modify: `docs/ELECTRON_WINDOWS_PLAN.md`
  - Replace stale references to missing scripts with the concrete scripts created in this plan.
- Modify: `docs/STATUS.md`
  - Add the pre-Windows preflight state and keep Windows/manual Excel gates explicitly open.

---

### Task 1: Add Windows Build Scripts

**Files:**
- Create: `desktop/build/build-sidecar-windows.bat`
- Create: `desktop/build/build-electron-windows.bat`
- Test: manual command inspection plus later Windows run

- [ ] **Step 1: Create `desktop/build/build-sidecar-windows.bat`**

Use `apply_patch` to create:

```bat
@echo off
setlocal

cd /d %~dp0\..\..

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
```

- [ ] **Step 2: Create `desktop/build/build-electron-windows.bat`**

Use `apply_patch` to create:

```bat
@echo off
setlocal

cd /d %~dp0\..\..

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
mkdir "%ELECTRON_BACKEND%"
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
```

- [ ] **Step 3: Verify scripts are tracked by git**

Run:

```bash
git status --short desktop/build
```

Expected:

```text
?? desktop/build/
```

- [ ] **Step 4: Commit**

Run:

```bash
git add desktop/build/build-sidecar-windows.bat desktop/build/build-electron-windows.bat
git commit -m "Add Windows desktop build scripts"
```

Expected: commit succeeds with two new files.

---

### Task 2: Add Electron Packaging Contract Validator

**Files:**
- Create: `desktop/electron_shell/scripts/check-packaging-contract.js`
- Modify: `desktop/electron_shell/package.json`
- Test: `npm run check:contract`

- [ ] **Step 1: Create validator script**

Create `desktop/electron_shell/scripts/check-packaging-contract.js`:

```javascript
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const packageJsonPath = path.join(root, "package.json");
const mainJsPath = path.join(root, "src", "main.js");

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exitCode = 1;
}

function requireIncludes(source, needle, label) {
  if (!source.includes(needle)) {
    fail(`${label} is missing required text: ${needle}`);
  }
}

function requireNotIncludes(source, needle, label) {
  if (source.includes(needle)) {
    fail(`${label} contains forbidden text: ${needle}`);
  }
}

const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
const mainJs = fs.readFileSync(mainJsPath, "utf8");

if (packageJson.main !== "src/main.js") {
  fail("package.json main must be src/main.js");
}

if (!packageJson.build || packageJson.build.productName !== "Warehouse Control Desk") {
  fail("Electron productName must remain Warehouse Control Desk until a deliberate rename pass.");
}

const extraResources = packageJson.build?.extraResources || [];
const hasBackendResource = extraResources.some((entry) => entry.from === "resources/backend" && entry.to === "backend");
if (!hasBackendResource) {
  fail("Electron build.extraResources must copy resources/backend to backend.");
}

const nsis = packageJson.build?.nsis || {};
if (nsis.perMachine !== false || nsis.allowElevation !== false) {
  fail("NSIS installer must stay per-user and must not require elevation.");
}

requireIncludes(mainJs, "findFreePort()", "src/main.js");
requireIncludes(mainJs, "process.resourcesPath", "src/main.js");
requireIncludes(mainJs, "WAREHOUSE_DATA_DIR", "src/main.js");
requireIncludes(mainJs, "DJANGO_DB_PATH", "src/main.js");
requireIncludes(mainJs, "WAREHOUSE_ENABLE_SHUTDOWN", "src/main.js");
requireIncludes(mainJs, "WAREHOUSE_SHUTDOWN_TOKEN", "src/main.js");
requireIncludes(mainJs, "X-Warehouse-Shutdown-Token", "src/main.js");
requireIncludes(mainJs, "requestSingleInstanceLock", "src/main.js");
requireIncludes(mainJs, "waitForHealthz", "src/main.js");
requireIncludes(mainJs, "processToStop.kill(\"SIGKILL\")", "src/main.js");
requireNotIncludes(mainJs, "localhost:8000", "src/main.js");
requireNotIncludes(mainJs, "127.0.0.1:8000", "src/main.js");

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log("Electron packaging contract OK");
```

- [ ] **Step 2: Add npm script**

Modify `desktop/electron_shell/package.json` scripts block to include `check:contract`:

```json
"scripts": {
  "start": "electron .",
  "check:contract": "node scripts/check-packaging-contract.js",
  "dist:win": "electron-builder --win nsis",
  "pack:win": "electron-builder --win dir"
}
```

- [ ] **Step 3: Run validator**

Run:

```bash
cd desktop/electron_shell
npm run check:contract
```

Expected:

```text
Electron packaging contract OK
```

- [ ] **Step 4: Run syntax check**

Run:

```bash
node --check desktop/electron_shell/src/main.js
node --check desktop/electron_shell/scripts/check-packaging-contract.js
```

Expected: no output and exit code `0`.

- [ ] **Step 5: Commit**

Run:

```bash
git add desktop/electron_shell/package.json desktop/electron_shell/scripts/check-packaging-contract.js
git commit -m "Add Electron packaging contract check"
```

Expected: commit succeeds.

---

### Task 3: Add Cross-Platform Sidecar Smoke Runner

**Files:**
- Create: `scripts/smoke_sidecar.py`
- Test: `python scripts/smoke_sidecar.py --command ...`

- [ ] **Step 1: Create smoke runner**

Create `scripts/smoke_sidecar.py`:

```python
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def request(url: str, *, method: str = "GET", token: str | None = None, timeout: float = 2.0) -> tuple[int, bytes]:
    headers = {}
    if token:
        headers["X-Warehouse-Shutdown-Token"] = token
    req = urllib.request.Request(url, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read()


def wait_for_healthz(base_url: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, body = request(f"{base_url}/healthz/")
            if status == 200 and b'"ok"' in body:
                return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"sidecar did not become healthy: {last_error}")


def terminate(process: subprocess.Popen[bytes], base_url: str, token: str) -> None:
    if process.poll() is not None:
        return
    try:
        request(f"{base_url}/shutdown/", method="POST", token=token, timeout=1.5)
    except Exception:
        pass
    try:
        process.wait(timeout=4)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        process.kill()
    else:
        process.send_signal(signal.SIGKILL)
    process.wait(timeout=4)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Meridian Python sidecar.")
    parser.add_argument("--command", nargs="+", required=True, help="Command to start the sidecar.")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--keep-data-dir", action="store_true")
    args = parser.parse_args()

    port = free_port()
    token = "smoke-token"
    temp_dir = Path(tempfile.mkdtemp(prefix="meridian-sidecar-smoke-"))
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "WAREHOUSE_APP_HOST": "127.0.0.1",
        "WAREHOUSE_APP_PORT": str(port),
        "WAREHOUSE_DATA_DIR": str(temp_dir),
        "DJANGO_DB_PATH": str(temp_dir / "db.sqlite3"),
        "DJANGO_DEBUG": "0",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "WAREHOUSE_AUTO_MIGRATE": "1",
        "WAREHOUSE_ENABLE_SHUTDOWN": "1",
        "WAREHOUSE_SHUTDOWN_TOKEN": token,
    }
    process = subprocess.Popen(args.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        wait_for_healthz(base_url, args.timeout)
        checks = [
            ("/", b"<html"),
            ("/export/items.xlsx", b"PK"),
        ]
        for path, expected in checks:
            status, body = request(f"{base_url}{path}", timeout=10)
            if status != 200:
                raise RuntimeError(f"{path} returned HTTP {status}")
            if expected not in body[:200]:
                raise RuntimeError(f"{path} response did not look valid")
        print(f"Sidecar smoke OK: {base_url}")
        return 0
    finally:
        terminate(process, base_url, token)
        if not args.keep_data_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            print(f"Data dir kept: {temp_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run source-sidecar smoke**

Run:

```bash
<repo>/.venv/bin/python scripts/smoke_sidecar.py --command <repo>/.venv/bin/python desktop/python_sidecar/serve.py
```

Expected:

```text
Sidecar smoke OK: http://127.0.0.1:<dynamic-port>
```

- [ ] **Step 3: Run Python syntax check**

Run:

```bash
<repo>/.venv/bin/python -m py_compile scripts/smoke_sidecar.py
```

Expected: no output and exit code `0`.

- [ ] **Step 4: Commit**

Run:

```bash
git add scripts/smoke_sidecar.py
git commit -m "Add sidecar smoke runner"
```

Expected: commit succeeds.

---

### Task 4: Add Windows Sidecar Smoke Script

**Files:**
- Create: `desktop/build/smoke-sidecar-windows.ps1`
- Test: script syntax review on macOS, actual execution later on Windows

- [ ] **Step 1: Create PowerShell smoke wrapper**

Create `desktop/build/smoke-sidecar-windows.ps1`:

```powershell
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
```

- [ ] **Step 2: Check file contents**

Run:

```bash
sed -n '1,220p' desktop/build/smoke-sidecar-windows.ps1
```

Expected: script contains `$SidecarPath`, `.venv\Scripts\python.exe`, and `scripts\smoke_sidecar.py`.

- [ ] **Step 3: Commit**

Run:

```bash
git add desktop/build/smoke-sidecar-windows.ps1
git commit -m "Add Windows sidecar smoke script"
```

Expected: commit succeeds.

---

### Task 5: Add Mac-Executable Pre-Windows Verification Command Set

**Files:**
- Modify: `scripts/README.md`
- Modify: `desktop/electron_shell/README.md`
- Modify: `docs/DESKTOP_APP.md`
- Test: run every command listed in the new Mac preflight section

- [ ] **Step 1: Update `scripts/README.md`**

Add this section:

```markdown
## Stage D Pre-Windows Preflight

Before moving to a real Windows machine, run from repo root:

```bash
<repo>/.venv/bin/python manage.py check
<repo>/.venv/bin/python manage.py test
<repo>/.venv/bin/python scripts/check_public_readiness.py
<repo>/.venv/bin/python scripts/smoke_sidecar.py --command <repo>/.venv/bin/python desktop/python_sidecar/serve.py
node --check desktop/electron_shell/src/main.js
node --check desktop/electron_shell/scripts/check-packaging-contract.js
cd desktop/electron_shell && npm run check:contract
```
```

- [ ] **Step 2: Update `desktop/electron_shell/README.md`**

Add this under `Development run`:

```markdown
Contract check:

```bash
npm run check:contract
```

This validates the Electron packaging assumptions: backend resource location, per-user NSIS settings, dynamic port selection, shutdown token, and no fixed `127.0.0.1:8000` dependency.
```

- [ ] **Step 3: Update `docs/DESKTOP_APP.md`**

Add this under Stage D status:

```markdown
Pre-Windows preflight should pass on macOS before switching to Windows:

- Django checks and full tests;
- public-readiness check;
- source sidecar smoke via `scripts/smoke_sidecar.py`;
- Electron main syntax check;
- Electron packaging contract check.
```

- [ ] **Step 4: Run documented commands**

Run:

```bash
<repo>/.venv/bin/python manage.py check
<repo>/.venv/bin/python manage.py test
<repo>/.venv/bin/python scripts/check_public_readiness.py
<repo>/.venv/bin/python scripts/smoke_sidecar.py --command <repo>/.venv/bin/python desktop/python_sidecar/serve.py
node --check desktop/electron_shell/src/main.js
node --check desktop/electron_shell/scripts/check-packaging-contract.js
cd desktop/electron_shell && npm run check:contract
```

Expected:

- `manage.py check`: `System check identified no issues`.
- `manage.py test`: all tests pass.
- `check_public_readiness.py`: public readiness passed.
- `smoke_sidecar.py`: `Sidecar smoke OK`.
- `node --check`: no output.
- `npm run check:contract`: `Electron packaging contract OK`.

- [ ] **Step 5: Commit**

Run:

```bash
git add scripts/README.md desktop/electron_shell/README.md docs/DESKTOP_APP.md
git commit -m "Document pre-Windows desktop preflight"
```

Expected: commit succeeds.

---

### Task 6: Add Stage D Pre-Windows Audit Gate

**Files:**
- Create: `docs/audits/2026-06-16-stage-d-prewindows-gate.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/ELECTRON_WINDOWS_PLAN.md`
- Test: public readiness

- [ ] **Step 1: Create audit gate note**

Create `docs/audits/2026-06-16-stage-d-prewindows-gate.md`:

```markdown
# Stage D Pre-Windows Gate

Date: 2026-06-16

## Scope

This gate records what can be verified before manual real Excel validation and before running the Windows installer on a real Windows machine.

## Verified Before Windows

- Django system check passes.
- Django test suite passes.
- Public readiness check passes.
- Source sidecar starts with a temporary data directory.
- Source sidecar responds on `/healthz/`.
- Source sidecar serves the dashboard.
- Source sidecar returns an `.xlsx` export payload.
- Electron main process syntax check passes.
- Electron packaging contract check passes.

## Still Manual

- Real client Excel workbooks must be validated manually when available.
- Windows sidecar build must be executed on a real Windows machine.
- Electron NSIS installer must be built on Windows.
- Per-user install without admin rights must be tested on Windows.
- First launch, shutdown, relaunch, Excel export, and data-dir persistence must be tested on Windows.

## Decision

Stage D is ready for a Windows packaging session after the preflight commands pass. This does not close `v0.6.0`; it only removes macOS-solvable uncertainty before the Windows run.
```

- [ ] **Step 2: Update `docs/ELECTRON_WINDOWS_PLAN.md` build flow**

Replace the current Build flow section with:

```markdown
## 8. Build flow

Mac preflight before switching to Windows:

```bash
<repo>/.venv/bin/python manage.py check
<repo>/.venv/bin/python manage.py test
<repo>/.venv/bin/python scripts/check_public_readiness.py
<repo>/.venv/bin/python scripts/smoke_sidecar.py --command <repo>/.venv/bin/python desktop/python_sidecar/serve.py
cd desktop/electron_shell && npm run check:contract
```

Windows flow:

1. Build Python sidecar:
   - `desktop\build\build-sidecar-windows.bat`
2. Smoke-test sidecar:
   - `powershell -ExecutionPolicy Bypass -File desktop\build\smoke-sidecar-windows.ps1`
3. Build Electron installer:
   - `desktop\build\build-electron-windows.bat`
4. Install through generated NSIS artifact without admin rights.
5. Verify first launch, shutdown, relaunch, Excel export, and data persistence.
```

- [ ] **Step 3: Update `docs/STATUS.md`**

Add under desktop/gui-app status:

```markdown
- Stage D pre-Windows preflight scripts are prepared:
  - Windows sidecar build script;
  - Windows Electron build script;
  - Windows sidecar smoke wrapper;
  - cross-platform sidecar smoke runner;
  - Electron packaging contract validator.
```

Add under known limitations:

```markdown
- Stage D pre-Windows preflight does not replace real Windows installer validation.
```

- [ ] **Step 4: Run public readiness**

Run:

```bash
<repo>/.venv/bin/python scripts/check_public_readiness.py
```

Expected:

```text
Public readiness check passed for <repo>
```

- [ ] **Step 5: Commit**

Run:

```bash
git add docs/audits/2026-06-16-stage-d-prewindows-gate.md docs/ELECTRON_WINDOWS_PLAN.md docs/STATUS.md
git commit -m "Record Stage D pre-Windows gate"
```

Expected: commit succeeds.

---

### Task 7: Final Verification and PR

**Files:**
- No new files unless verification reveals failures.
- Test: full verification stack.

- [ ] **Step 1: Run full verification**

Run:

```bash
<repo>/.venv/bin/python manage.py check
<repo>/.venv/bin/python manage.py test
<repo>/.venv/bin/python scripts/check_public_readiness.py
<repo>/.venv/bin/python scripts/smoke_sidecar.py --command <repo>/.venv/bin/python desktop/python_sidecar/serve.py
node --check desktop/electron_shell/src/main.js
node --check desktop/electron_shell/scripts/check-packaging-contract.js
cd desktop/electron_shell && npm run check:contract
git diff --check
```

Expected:

- Django check passes.
- Django tests pass.
- Public readiness passes.
- Sidecar smoke passes.
- Node syntax checks pass.
- Electron contract passes.
- Git whitespace check passes.

- [ ] **Step 2: Inspect status**

Run:

```bash
git status --short --branch
git log --oneline -8
```

Expected:

- Branch contains only the planned commits.
- Working tree is clean.

- [ ] **Step 3: Push branch**

Run:

```bash
git push -u origin stage-d-prewindows-preflight
```

Expected: branch is pushed.

- [ ] **Step 4: Create PR**

Run:

```bash
gh pr create --title "Prepare Stage D pre-Windows packaging preflight" --body "## Summary
- add Windows sidecar and Electron build scripts
- add sidecar smoke runner and Electron packaging contract check
- document Stage D pre-Windows verification and remaining manual gates

## Verification
- manage.py check
- manage.py test
- scripts/check_public_readiness.py
- scripts/smoke_sidecar.py
- node --check desktop/electron_shell/src/main.js
- node --check desktop/electron_shell/scripts/check-packaging-contract.js
- npm run check:contract
- git diff --check"
```

Expected: PR URL is printed.

- [ ] **Step 5: Check Gemini comments**

Run:

```bash
gh pr view <PR_NUMBER> --json url,state,mergeable,reviewDecision,comments,reviews,headRefOid
gh api repos/k-kostin/meridian/pulls/<PR_NUMBER>/comments
gh api repos/k-kostin/meridian/issues/<PR_NUMBER>/comments
```

Expected:

- If comments are empty or non-actionable, proceed to merge.
- If Gemini reports a valid issue, fix it in a follow-up commit, rerun verification, push, and re-check comments.

- [ ] **Step 6: Merge PR**

Run:

```bash
gh pr merge <PR_NUMBER> --squash --delete-branch
```

Expected:

- PR is merged.
- Local `main` fast-forwards.
- `git status --short --branch` reports `main...origin/main`.

---

## Self-Review

Spec coverage:

- Close maximum questions before manual Excel validation: covered by synthetic-independent smoke runner, docs gate, and explicit manual Excel remaining gate.
- Close maximum questions before Windows machine: covered by Windows build scripts, smoke wrapper, Electron contract validator, and macOS preflight commands.
- Avoid running real Windows work on macOS: explicitly deferred to manual Windows stage.
- Keep Electron as primary path and Tauri experimental: preserved in docs and scripts.

Placeholder scan:

- No `TBD`, `TODO`, `implement later`, or vague “add validation” steps.
- Every code task includes exact file paths, code snippets, commands, and expected outcomes.

Type/signature consistency:

- `scripts/smoke_sidecar.py` command shape matches PowerShell wrapper.
- `npm run check:contract` matches `package.json` script.
- Windows build scripts use `desktop\build\...` paths referenced in docs.
- Electron contract checks existing `src/main.js` tokens introduced by the current Stage D scaffold.

## Execution Handoff

Plan complete. Use either:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using the inline implementation-plan workflow, batch execution with checkpoints.
