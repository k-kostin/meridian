# Stage C Audit and Deployment Limits Implementation Plan

> **For agentic workers:** Use this plan with an implementation workflow and keep the scope narrow. Do not add Real Excel onboarding validation in this slice.

**Goal:** Finish the Stage C pilot-readiness slice for operational audit hardening, explicit Local Single User deployment limits, and a short Stage C audit gate.

**Architecture:** Extend the existing `ActivityEvent` operational timeline rather than adding a second audit system. Keep the audit trail pilot-grade and mutable by normal database access; do not describe it as immutable, forensic, or security-grade. Surface deployment limits in the product UI and docs so SQLite remains a supported Local Single User profile, not a multi-user production promise.

**Tech Stack:** Django 6, SQLite, Django ORM migrations, server-rendered templates, existing docs and verification scripts.

---

## Files

- Modify `warehouse_app/models.py`: add operational event types.
- Modify `warehouse_app/activity.py`: add focused event recorders for imports, backups, demo reload, and reference edits.
- Modify `warehouse_app/views.py`: call audit recorders from existing successful flows.
- Modify `warehouse_app/tests.py`: cover new audit events and deployment limits UI.
- Modify `templates/base.html`: expose a compact Local Single User deployment notice.
- Modify `templates/warehouse_app/dashboard.html`: show deployment profile boundaries.
- Modify `docs/TECH_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/STATUS.md`, `README.md`: align Stage C status and explicit deployment limits.
- Create `docs/audits/2026-06-10-stage-c-audit-gate.md`: short gate result after verification.

## Task 1: Operational Audit Event Types and Helpers

- [x] Add event types for successful operational actions that matter in a pilot: item import committed, opening inventory import committed, manual backup created, demo data reset, reference record changed.
- [x] Add record helper functions in `warehouse_app/activity.py` with stable `actor_label` and compact JSON metadata.
- [x] Keep helper names explicit and narrow. Do not implement immutable audit semantics.

## Task 2: Wire Audit Events Into Existing Flows

- [x] Record item import commits only after a successful commit with no errors.
- [x] Record opening inventory import commits only after an inventory draft is created.
- [x] Record manual backup creation after `create_local_backup()` succeeds.
- [x] Record demo reset after `seed_demo_data(reset=True)` succeeds.
- [x] Record reference edits for unit, warehouse, item category, and item create/update flows where they already save successfully.

## Task 3: Deployment Limits UI

- [x] Add a compact deployment-profile notice visible from the main shell or dashboard.
- [x] State three things plainly: SQLite, one local computer, one active operator.
- [x] Do not block workflows or add configuration complexity in this slice.

## Task 4: Documentation and Stage C Audit Gate

- [x] Update docs so Stage C says audit hardening and deployment limits are implemented.
- [x] Keep Real Excel onboarding validation explicitly deferred until the user starts it.
- [x] Add the Stage C audit gate file with evidence, remaining risks, and the next slice.

## Task 5: Verification and PR

- [x] Run targeted tests for audit/deployment changes.
- [x] Run full Django tests, Django check, public readiness, and whitespace checks.
- [ ] Push branch, create PR, wait for Gemini comments, address actionable comments before merge.
