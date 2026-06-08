# v0.4.0 Stage B Closure Audit Plan

> **For maintainers:** execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Stage B as `v0.4.0` only after version metadata, docs, release notes, and verification evidence agree.

**Architecture:** This is a release/audit gate, not a feature slice. It must not change warehouse accounting behavior; it only records the merged Stage B operational contour and proves the current tree is consistent.

**Tech Stack:** Django, SQLite, server-rendered templates, Electron shell metadata, project docs/release notes, existing verification scripts.

---

## Task 1: Verify PR #17 Is Merged And Main Is Current

**Files:**
- Inspect: git state and GitHub PR state.

- [ ] **Step 1: Check local branch**

Run:

```bash
git status --short --branch
```

Expected:

```text
## main...origin/main
```

- [ ] **Step 2: Check PR #17**

Run:

```bash
gh pr view 17 --json state,mergeCommit,url
```

Expected: PR state is `MERGED`.

## Task 2: Bump Milestone Version

**Files:**
- Modify: `warehouse_app/version.py`
- Modify: `desktop/electron_shell/package.json`
- Modify: `docs/DESKTOP_APP.md`

- [ ] **Step 1: Set app version**

Set:

```python
APP_VERSION = "0.4.0"
APP_VERSION_LABEL = f"v{APP_VERSION}"
```

- [ ] **Step 2: Set Electron package version**

Set:

```json
"version": "0.4.0"
```

- [ ] **Step 3: Update desktop docs current version**

Set the current version reference in `docs/DESKTOP_APP.md` to:

```markdown
Текущая версия: `0.4.0`.
```

## Task 3: Close Stage B In Docs

**Files:**
- Modify: `docs/STATUS.md`
- Modify: `docs/TECH_SPEC.md`
- Modify: `docs/ROADMAP.md`
- Create: `docs/releases/v0.4.0-stage-b-closure.md`

- [ ] **Step 1: Update STATUS**

Record that Stage B operational contour is closed as `v0.4.0`, and move implemented Stage B features out of known limitations:

- import column aliases;
- item import update mode;
- explicit unit auto-create mode;
- item categories;
- category-aware operational filters and exports;
- user saved views for documents and balances.

- [ ] **Step 2: Update TECH_SPEC**

Move Stage B requirements from uncertain/future wording into confirmed/implemented sections:

- flexible item import column aliases;
- explicit update-existing import mode;
- explicit unit auto-create import mode;
- item categories;
- category filters for item list, balances, daily/monthly ledgers, analytics, and Excel exports;
- saved views for documents and balances.

- [ ] **Step 3: Update ROADMAP**

Mark Stage B as closed, preserve real deferrals, and keep Stage C as the next product line.

- [ ] **Step 4: Add release note**

Create `docs/releases/v0.4.0-stage-b-closure.md` with the included slices, verification evidence, and do-not-regress invariants.

## Task 4: Verification Gate

**Files:**
- Inspect: test output, verifier output, diff.

- [ ] **Step 1: Run Django system check**

Run:

```bash
python manage.py check
```

Expected:

```text
System check identified no issues
```

- [ ] **Step 2: Run full tests**

Run:

```bash
python manage.py test
```

Expected: all tests pass.

- [ ] **Step 3: Run project verifiers**

Run:

```bash
python scripts/check_changed.py --full
python scripts/check_public_readiness.py
python -m unittest discover -s scripts -p 'test_check_public_readiness.py'
git diff --check
```

Expected: all commands pass.

## Task 5: Commit And PR

**Files:**
- Stage all Task 2-3 edits.

- [ ] **Step 1: Commit**

Run:

```bash
git add warehouse_app/version.py desktop/electron_shell/package.json docs/DESKTOP_APP.md docs/STATUS.md docs/TECH_SPEC.md docs/ROADMAP.md docs/releases/v0.4.0-stage-b-closure.md docs/plans/2026-06-08-stage-b-closure-audit-plan.md
git commit -m "release: mark v0.4.0 stage b closure"
```

- [ ] **Step 2: Push and open PR**

Run:

```bash
git push -u origin stage-b-v0.4-closure
gh pr create --base main --head stage-b-v0.4-closure --title "Release v0.4.0 Stage B closure" --body-file /tmp/stage-b-v0.4-pr.md
```

Expected: PR URL is created.

## Self-Review

- PR #17 merged before closure work starts.
- Version is `0.4.0` in app and Electron metadata.
- Docs no longer claim Stage B features are future limitations.
- Release note exists and names the merged Stage B slices.
- Verification commands pass before PR creation.
