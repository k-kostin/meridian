# Stage A Audit Gate - 2026-06-04

## Scope

This audit verifies whether Stage A stabilization can be treated as closed before starting Stage B operational work.

Stage A areas:

- workflow hardening;
- UX hardening visible in the current MVP;
- role-aware pilot permissions;
- activity timeline;
- built-in presets;
- Excel import foundation, preview, commit flow, and opening inventory import;
- documentation and public repository hygiene.

## Baseline

- Branch audited: `v0.3-stage-a-audit`
- Base branch: `main`
- Base commit: `401aaf5`

## Deterministic Verification

Commands were run with the local project virtualenv Python used for this workspace.

| Check | Result |
| --- | --- |
| `python manage.py check` | PASS - `System check identified no issues` |
| `python manage.py test` | PASS - 111 tests OK |
| `python scripts/check_changed.py --full` | PASS - 111 tests OK |
| `python scripts/check_public_readiness.py` | PASS |
| `git diff --check` | PASS |

Note: `scripts/check_public_readiness.py` was missing from the public repository even though older release notes referenced it. The audit restored this guardrail before treating public hygiene as verified.

## Documentation Consistency

Checked:

- `README.md`
- `docs/TECH_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- `docs/releases/*.md`
- `warehouse_app/urls.py`
- templates exposing import and role-aware actions

Result:

- PASS after doc-only reconciliation.
- Updated stale `docs/STATUS.md` wording that still described the current development branch as `v0.3 Import Foundation`.
- Moved the already implemented Django admin protection for posted documents from unresolved questions to fixed business rules in `docs/TECH_SPEC.md`.

## Public Hygiene

Checked:

- internal agent/process terms;
- secrets and tokens;
- local absolute paths;
- generated artifacts and local databases;
- ignored files;
- restored `scripts/check_public_readiness.py`.

Result:

- PASS.
- The restored public readiness checker passes.
- `Warehouse Control Desk` remains in desktop/release internals as an accepted legacy product label; it is not present in the public README heading.
- Secret/password scan hits are expected template CSRF tokens, test passwords, settings/env-var names, and checker patterns, not real credentials.
- Local path blacklist terms appear only in `scripts/check_public_readiness.py`, which intentionally carries the public hygiene rules.

## Browser Smoke

Environment:

- `WAREHOUSE_DEMO_MODE=1`
- `DJANGO_DEBUG=0`
- `DJANGO_DB_PATH=/tmp/meridian-stage-a-audit/db.sqlite3`
- URL: `http://127.0.0.1:8000/`

Checked pages:

- dashboard;
- nomenclature;
- movement documents;
- inventories;
- balances;
- days;
- months;
- analytics;
- item import;
- opening inventory import;
- non-debug 404.

Result:

- PASS.
- Core pages rendered nonblank in the in-app Browser with expected titles/text and without traceback/debug output.
- `/nonexistent-page/` returned a non-debug 404 page.
- Static CSS returned `200 OK` when the smoke server was run with `--insecure`, matching the existing demo/prod run scripts.
- Document posting form for draft document `23` has `onsubmit="return confirm(...)"`.
- Inventory posting form for draft inventory `3` has `onsubmit="return confirm(...)"`.
- Runtime note: repo-root `db.sqlite3` creation was not used for smoke; the browser run used a temporary SQLite database under `/tmp/meridian-stage-a-audit/`.

## Excel Import/Export Smoke

Generated local workbooks:

- `/tmp/meridian-stage-a-audit/items-import.xlsx`
- `/tmp/meridian-stage-a-audit/opening-import.xlsx`

Checked flows:

- item import preview and commit;
- opening inventory import preview and commit;
- item export;
- balances export;
- movement export;
- inventory export;
- workbook readability with `openpyxl`.

Result:

- PASS.
- Item import preview and commit created `AUDIT-SKU-001` and `AUDIT-SKU-002` through the existing `/items/import/` view.
- Opening inventory import preview and commit created draft full inventory `4`; imported line preserved comment `opening audit row`.
- Export responses returned `.xlsx` payloads with filenames `items.xlsx`, `balances.xlsx`, `movements.xlsx`, and `inventories.xlsx`.
- Export workbooks were readable through `openpyxl`.

Notes:

- The in-app Browser wrapper available in this session did not expose file upload support, so `.xlsx` upload smoke used Django `Client` against the same HTTP views.
- The item import workbook must use header `Единица`; abbreviated `Ед.изм.` is not currently accepted. This is safe to leave unless pilot users need flexible column mapping.

## Findings

### Must fix before Stage A closure

None.

### Safe to leave for Stage B or later

- In-app Browser automation in this session could not upload files; real `.xlsx` upload was verified through Django `Client` against the same HTTP views.
- Item import accepts the exact `Единица` header, not the abbreviated `Ед.изм.` header. Flexible column mapping can remain a later import enhancement.
- With `DJANGO_DEBUG=0`, local `runserver` must use `--insecure` for static files in demo-style runs. Existing run scripts already do this.

## Final Verdict

PASS.

Stage A stabilization can be treated as closed. The project is ready to move to Stage B operational contour work.
