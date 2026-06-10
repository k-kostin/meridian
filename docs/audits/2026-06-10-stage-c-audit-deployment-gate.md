# Stage C Audit/Deployment Gate

Date: 2026-06-10

Scope: Stage C commercial pilot readiness slice for operational audit hardening and Local Single User deployment limits.

Out of scope by explicit sequencing: Real Excel onboarding validation. It remains the next Stage C slice and must start only after a separate user command with real or realistic `.xlsx` files.

## Verdict

Passed for the audit/deployment slice.

The project now has enough pilot-grade operational traceability and visible Local Single User boundaries to continue toward real Excel onboarding validation. This does not close all of Stage C and does not make the product production-grade.

## Evidence

- `ActivityEvent` remains the single operational timeline model and now covers successful posting, item import commits, opening inventory import commits, manual backup creation, demo data load/reset and reference record changes.
- `ActivityEvent.warehouse` is nullable so global operational actions do not need fake warehouse attribution.
- Actor attribution is stored when the action comes from an authenticated user; anonymous local/demo flows remain supported.
- Dashboard shows the Local Single User boundary: SQLite, one local computer, one active operator, and no simultaneous multi-user promise.
- Docs now state that current audit is pilot-grade operational history, not immutable or security-grade audit logging.
- Docs now state that Team / Multi-User remains a future server/PostgreSQL deployment profile using the same domain core.

## Verification

- Targeted audit/deployment tests: 18 tests OK.
- Full Django tests: 160 tests OK.
- `python manage.py check`: OK.
- `git diff --check`: OK.
- Browser smoke: dashboard opened at `http://127.0.0.1:8000/`; Local Single User notice present in rendered HTML.
- Public readiness: passed after removing local generated artifacts.

## Remaining Stage C Work

- Real Excel onboarding validation on real or realistic client files.
- Any import alias/mapping improvements should come from those files, not imagined ERP scenarios.

## Explicit Non-Goals

- No security-grade immutable audit log.
- No production-grade multi-user SQLite claim.
- No web restore UI, scheduled backups, encryption or cloud backup in this slice.
- No separate SQLite/PostgreSQL business-logic fork.
