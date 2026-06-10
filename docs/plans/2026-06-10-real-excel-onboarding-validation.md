# Real Excel Onboarding Validation Plan

Goal: make the existing Excel onboarding flow less brittle against realistic workbook shapes before testing real client files.

This is a narrow `v0.5.0` pilot-readiness slice. It must not add a new import product area, bypass preview/validation, write stock directly, or auto-post inventory documents.

## Scope

- Use synthetic but realistic `.xlsx` workbooks to cover common non-ideal Excel files.
- Keep imports server-side and preview-first.
- Keep item import semantics unchanged:
  - create-only by default;
  - explicit update mode for existing items;
  - optional unit auto-create.
- Keep opening stock import semantics unchanged:
  - create a draft full inventory;
  - require one warehouse per import;
  - user reviews and posts manually.
- Leave validation on real client files as the next manual step.

## Realistic Cases To Support Now

1. Sheet names:
   - item import can read `Номенклатура`, `Товары`, `Справочник`, `Items`, or active sheet;
   - opening stock import can read `Стартовые остатки`, `Остатки`, `Остатки склада`, `Opening stock`, or active sheet.
2. Header shapes:
   - case-insensitive headers;
   - extra spaces and non-breaking spaces;
   - punctuation variants such as `Ед. изм.`, `Кол-во`, `Факт. остаток`;
   - common business labels such as `Код товара`, `Наименование товара`, `Товар`, `Код склада`.
3. UX wording:
   - show compact accepted-sheet and accepted-column guidance near import forms;
   - keep warnings clear that preview does not change data.

## Implementation Steps

1. Add parser tests for realistic item workbooks:
   - workbook has a non-data active sheet and a data sheet named `Товары`;
   - headers use `Код товара`, `Наименование товара`, `Ед. изм.`, `Активность`, `Примечание`.
2. Add parser tests for realistic opening-stock workbooks:
   - workbook has a non-data active sheet and a data sheet named `Остатки`;
   - headers use `Код склада`, `Код товара`, `Кол-во`, `Примечание`.
3. Implement a small workbook sheet selector in `warehouse_app/imports.py`.
4. Implement conservative header normalization in `warehouse_app/imports.py`.
5. Extend import column aliases only for labels covered by tests.
6. Update form help text and import preview cards.
7. Update `TECH_SPEC.md`, `STATUS.md`, and `ROADMAP.md` to mark this synthetic validation slice as implemented and real-file validation as pending.
8. Run targeted import tests, full Django tests, system check, public-readiness check, and whitespace diff check.

## Acceptance Criteria

- Synthetic realistic item import parses without row-level required-field errors.
- Synthetic realistic opening-stock import parses without row-level required-field errors.
- Existing import behavior and validation tests still pass.
- Docs clearly distinguish implemented synthetic validation from pending real-file validation.
- No private local paths or internal agent workflow wording are added to public docs.

## Out Of Scope

- Multi-warehouse opening-stock import in one file.
- User-driven column mapping UI.
- Import from `.xls`, `.csv`, Google Sheets, ERP exports, or zipped folders.
- Direct stock writes.
- Auto-posting imported opening inventory.
- Client-side index work.
