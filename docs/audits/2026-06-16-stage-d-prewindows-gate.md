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
