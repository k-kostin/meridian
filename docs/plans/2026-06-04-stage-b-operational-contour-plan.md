# Stage B Operational Contour Implementation Plan

> **For implementers:** execute this plan task-by-task. Keep changes small, test each slice before committing, and preserve the `v0.1` baseline plus the `v0.3.0` Stage A closure invariants.

**Goal:** Build the `v0.4.0` operational contour by tightening the current day-to-day workflows: scope reconciliation, import flexibility, category-based item organization, report filters, and saved views.

**Architecture:** Keep the Django server-rendered monolith. Add small domain/service helpers where needed, but do not move business rules into templates or client-side code. Every slice must keep calculated balances, inventory-as-adjustment, role checks, and import preview/validation semantics intact.

**Tech Stack:** Django, SQLite, Django ORM, server-rendered templates, openpyxl, existing `warehouse_app` models/forms/views/tests.

---

## Stage B Scope Decision

Stage B should not re-implement already closed work. The current code already contains:

- draft editing for movement documents;
- draft editing for inventories;
- transfer documents between warehouses;
- built-in quick filter presets;
- basic role-aware UX and server-side write guards.

Therefore Stage B should start with documentation reconciliation and then focus on features still listed as open:

- flexible import column aliases;
- optional import update mode for existing items;
- optional auto-create units during item import;
- category support for nomenclature;
- category-aware list/report filters;
- user saved views after existing built-in presets.

Do not include desktop packaging in this plan. That remains a parallel infrastructure track.

## File Structure

- Modify `docs/ROADMAP.md`
  - reconcile Stage B scope and remove already-completed items from the active priority list.
- Modify `docs/TECH_SPEC.md`
  - move confirmed Stage B requirements into confirmed requirements before implementation.
  - keep uncertain items in "not fixed yet" until implemented.
- Modify `docs/STATUS.md`
  - track Stage B slices and known limits after each merge.
- Create release notes under `docs/releases/`
  - one short release note per slice, final `v0.4.0` closure note at the end.
- Modify `warehouse_app/imports.py`
  - add column alias handling.
  - add optional item update planning/commit behavior.
  - add optional unit auto-create behavior.
- Modify `warehouse_app/forms.py`
  - add explicit import mode controls only when the backend supports them.
  - add item category form fields after the category model exists.
- Modify `warehouse_app/models.py`
  - add `ItemCategory` and an optional `Item.category` foreign key.
  - add saved view model only after category/filter work is stable.
- Create migrations in `warehouse_app/migrations/`
  - category model and item category relation.
  - saved view model if implemented in the same stage.
- Modify `warehouse_app/views.py`
  - wire import modes.
  - add category filters.
  - add saved view list/apply/create/delete endpoints if implemented.
- Modify templates in `templates/warehouse_app/`
  - item list category UI.
  - report filter category UI.
  - saved view chips/dropdowns.
- Modify `warehouse_app/services.py`
  - add category filter support to report/balance query builders only through explicit parameters.
- Modify `warehouse_app/tests.py`
  - add focused tests for each slice.

---

## Task 1: Reconcile Stage B Scope In Docs

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/TECH_SPEC.md`
- Modify: `docs/STATUS.md`
- Create: `docs/releases/v0.4-stage-b-kickoff.md`

- [ ] **Step 1: Update ROADMAP Stage B priorities**

Replace the active Stage B priority list in `docs/ROADMAP.md` with:

```markdown
Приоритет:

1. Reconcile уже закрытых Stage B-кандидатов:
   - редактирование черновиков уже реализовано;
   - перемещения между складами уже реализованы;
   - встроенные быстрые фильтры уже реализованы.
2. Расширение импорта номенклатуры:
   - поддержать распространенные алиасы колонок;
   - затем отдельно добавить обновление существующих позиций, если это нужно для пилота;
   - затем отдельно добавить auto-create единиц, если это нужно для пилота.
3. Категории номенклатуры и фильтры по категориям.
4. Пользовательские сохраненные представления поверх существующих встроенных presets.
5. Расширение ролей до production-grade пользовательского контура только после появления реального требования.
```

- [ ] **Step 2: Update TECH_SPEC open questions**

In `docs/TECH_SPEC.md`, keep import update, auto-create units, categories, saved views, and production RBAC under "Не зафиксировано окончательно" until each slice is implemented. Add a Stage B note:

```markdown
- Stage B не должен переоткрывать уже реализованные функции: редактирование черновиков, перемещения между складами и встроенные быстрые фильтры.
```

- [ ] **Step 3: Add kickoff release note**

Create `docs/releases/v0.4-stage-b-kickoff.md`:

```markdown
# v0.4 Stage B Kickoff

Date: 2026-06-04

## Purpose

Start the Stage B operational contour line after `v0.3.0` Stage A closure.

## Scope

Stage B focuses on day-to-day operational improvements, not desktop packaging and not analytics dashboards.

## Confirmed Starting Point

- Draft editing for movement documents is already implemented.
- Draft editing for inventories is already implemented.
- Transfer documents are already implemented.
- Built-in quick filter presets are already implemented.

## Next Slices

1. Import column aliases.
2. Optional item update mode during import.
3. Optional unit auto-create during import.
4. Item categories.
5. Category-aware filters.
6. User saved views.

## Do Not Regress

Preserve `v0.1 MVP Baseline` and `v0.3.0 Stage A Closure` invariants.
```

- [ ] **Step 4: Run public docs checks**

Run:

```bash
python scripts/check_public_readiness.py
git diff --check
```

Expected:

```text
Public readiness check passed for /Users/kirillkostin/Projects/meridian-public
```

- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP.md docs/TECH_SPEC.md docs/STATUS.md docs/releases/v0.4-stage-b-kickoff.md
git commit -m "docs: reconcile stage b scope"
```

---

## Task 2: Add Import Column Aliases

**Files:**
- Modify: `warehouse_app/imports.py`
- Modify: `warehouse_app/forms.py`
- Modify: `templates/warehouse_app/item_import_preview.html`
- Modify: `templates/warehouse_app/opening_inventory_import_preview.html`
- Modify: `warehouse_app/tests.py`
- Create: `docs/releases/v0.4-import-column-aliases.md`

**Purpose:** Accept common Excel column labels without changing import semantics.

Supported item import aliases:

- `Артикул`: `Артикул`, `SKU`, `Код`, `Код номенклатуры`
- `Наименование`: `Наименование`, `Название`, `Номенклатура`
- `Единица`: `Единица`, `Ед.изм.`, `Ед изм`, `Единица измерения`
- `Активна`: `Активна`, `Активен`, `Действует`
- `Комментарий`: `Комментарий`, `Примечание`

Supported opening inventory aliases:

- `Склад`: `Склад`, `Код склада`, `Warehouse`
- `Артикул`: `Артикул`, `SKU`, `Код`, `Код номенклатуры`
- `Фактическое количество`: `Фактическое количество`, `Количество`, `Остаток`, `Факт`
- `Комментарий`: `Комментарий`, `Примечание`

- [ ] **Step 1: Write failing tests for item aliases**

Add to `warehouse_app/tests.py`:

```python
    def test_item_import_accepts_common_column_aliases(self):
        admin = User.objects.create_user(username="alias-admin", password="pass")
        UserProfile.objects.create(user=admin, role=UserRole.ADMIN)
        self.client.force_login(admin)

        workbook = self._import_workbook_upload(
            [["ALIAS-001", "Позиция с алиасами", self.unit.code, "да", "алиас"]],
            headers=["SKU", "Название", "Ед.изм.", "Действует", "Примечание"],
        )

        response = self.client.post("/items/import/", {"workbook": workbook})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ALIAS-001")
        self.assertNotContains(response, "Единица обязательна")
```

Run:

```bash
python manage.py test warehouse_app.tests.WarehouseAppTests.test_item_import_accepts_common_column_aliases
```

Expected before implementation:

```text
FAIL
```

- [ ] **Step 2: Write failing tests for opening inventory aliases**

Add to `warehouse_app/tests.py`:

```python
    def test_opening_inventory_import_accepts_common_column_aliases(self):
        operator = User.objects.create_user(username="opening-alias-operator", password="pass")
        UserProfile.objects.create(user=operator, role=UserRole.OPERATOR)
        self.client.force_login(operator)

        workbook = self._opening_inventory_workbook_upload(
            [[self.warehouse.code, self.item.sku, "12", "остаток"]],
            headers=["Код склада", "SKU", "Остаток", "Примечание"],
        )

        response = self.client.post("/inventories/import-opening/", {"workbook": workbook})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.item.sku)
        self.assertNotContains(response, "Фактическое количество обязательно")
```

Run:

```bash
python manage.py test warehouse_app.tests.WarehouseAppTests.test_opening_inventory_import_accepts_common_column_aliases
```

Expected before implementation:

```text
FAIL
```

- [ ] **Step 3: Add alias maps in `imports.py`**

Add near the existing required column constants:

```python
ITEM_COLUMN_ALIASES = {
    "Артикул": ["Артикул", "SKU", "Код", "Код номенклатуры"],
    "Наименование": ["Наименование", "Название", "Номенклатура"],
    "Единица": ["Единица", "Ед.изм.", "Ед изм", "Единица измерения"],
    "Активна": ["Активна", "Активен", "Действует"],
    "Комментарий": ["Комментарий", "Примечание"],
}

OPENING_INVENTORY_COLUMN_ALIASES = {
    "Склад": ["Склад", "Код склада", "Warehouse"],
    "Артикул": ["Артикул", "SKU", "Код", "Код номенклатуры"],
    "Фактическое количество": ["Фактическое количество", "Количество", "Остаток", "Факт"],
    "Комментарий": ["Комментарий", "Примечание"],
}
```

- [ ] **Step 4: Replace `_cell` with alias-aware helper**

In `warehouse_app/imports.py`, add:

```python
def _cell_with_aliases(row, headers: dict[str, int], column: str, aliases: dict[str, list[str]]) -> str:
    for candidate in aliases.get(column, [column]):
        value = _cell(row, headers, candidate)
        if value:
            return value
    return ""
```

Then replace item parser calls like:

```python
sku = _cell(values, headers, "Артикул")
```

with:

```python
sku = _cell_with_aliases(values, headers, "Артикул", ITEM_COLUMN_ALIASES)
```

Do the same for all item and opening inventory import columns.

- [ ] **Step 5: Update import help text**

In `warehouse_app/forms.py`, change item import help text to:

```python
self.fields["workbook"].help_text = "Ожидается лист «Номенклатура» или активный лист. Поддерживаются колонки: Артикул/SKU, Наименование/Название, Единица/Ед.изм., Активна, Комментарий."
```

Change opening import help text to:

```python
self.fields["workbook"].help_text = "Ожидается лист «Стартовые остатки» или активный лист. Поддерживаются колонки: Склад/Код склада, Артикул/SKU, Фактическое количество/Остаток, Комментарий."
```

- [ ] **Step 6: Add release note**

Create `docs/releases/v0.4-import-column-aliases.md`:

```markdown
# v0.4 Import Column Aliases

Date: 2026-06-04

## Purpose

Make Excel import less brittle by accepting common column aliases.

## Changes

- Item import accepts `SKU`, `Название`, and `Ед.изм.` style headers.
- Opening inventory import accepts `Код склада`, `SKU`, and `Остаток` style headers.
- Import still uses preview/validation and does not bypass domain rules.

## Do Not Regress

Imports must still report row-level validation errors before commit.
Opening stock import must still create a draft full inventory, not direct stock rows.
```

- [ ] **Step 7: Run tests**

```bash
python manage.py test warehouse_app.tests.WarehouseAppTests.test_item_import_accepts_common_column_aliases warehouse_app.tests.WarehouseAppTests.test_opening_inventory_import_accepts_common_column_aliases
python manage.py test
python scripts/check_changed.py --full
python scripts/check_public_readiness.py
git diff --check
```

Expected:

```text
OK
Public readiness check passed
```

- [ ] **Step 8: Commit**

```bash
git add warehouse_app/imports.py warehouse_app/forms.py warehouse_app/tests.py docs/releases/v0.4-import-column-aliases.md
git commit -m "feat: support import column aliases"
```

---

## Task 3: Add Item Import Update Mode

**Files:**
- Modify: `warehouse_app/imports.py`
- Modify: `warehouse_app/forms.py`
- Modify: `warehouse_app/views.py`
- Modify: `templates/warehouse_app/item_import_preview.html`
- Modify: `warehouse_app/tests.py`
- Create: `docs/releases/v0.4-item-import-update-mode.md`

**Purpose:** Let admins update existing item names, units, active flag, and notes from Excel after preview. This must be explicit and must not happen in the default create-only import flow.

- [ ] **Step 1: Define import mode constants in `imports.py`**

Add:

```python
ITEM_IMPORT_MODE_CREATE_ONLY = "create_only"
ITEM_IMPORT_MODE_UPDATE_EXISTING = "update_existing"
ITEM_IMPORT_MODES = {ITEM_IMPORT_MODE_CREATE_ONLY, ITEM_IMPORT_MODE_UPDATE_EXISTING}
```

- [ ] **Step 2: Write failing validation test for default create-only behavior**

Add to `warehouse_app/tests.py`:

```python
    def test_item_import_create_only_still_rejects_existing_sku(self):
        admin = User.objects.create_user(username="create-only-admin", password="pass")
        UserProfile.objects.create(user=admin, role=UserRole.ADMIN)
        self.client.force_login(admin)

        workbook = self._import_workbook_upload([[self.item.sku, "Новое имя", self.unit.code, "да", ""]])

        response = self.client.post("/items/import/", {"workbook": workbook})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Артикул уже существует")
```

- [ ] **Step 3: Write failing update mode commit test**

Add:

```python
    def test_item_import_update_mode_updates_existing_item(self):
        admin = User.objects.create_user(username="update-mode-admin", password="pass")
        UserProfile.objects.create(user=admin, role=UserRole.ADMIN)
        self.client.force_login(admin)

        workbook = self._import_workbook_upload([[self.item.sku, "Обновленное имя", self.unit.code, "нет", "обновлено"]])

        response = self.client.post(
            "/items/import/",
            {"action": "commit", "import_mode": "update_existing", "workbook": workbook},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, "Обновленное имя")
        self.assertFalse(self.item.is_active)
        self.assertEqual(self.item.notes, "обновлено")
        self.assertContains(response, "Импорт обновил позиций: 1")
```

- [ ] **Step 4: Add mode-aware validation**

Change `validate_items_import_result` signature:

```python
def validate_items_import_result(result: ItemImportResult, *, import_mode: str = ITEM_IMPORT_MODE_CREATE_ONLY) -> list[ImportErrorDetail]:
```

Keep duplicate-in-file and unit checks for all modes. Only emit `"Артикул уже существует"` when `import_mode == ITEM_IMPORT_MODE_CREATE_ONLY`.

- [ ] **Step 5: Add mode-aware commit result**

Change `ItemImportCommitResult`:

```python
@dataclass(frozen=True)
class ItemImportCommitResult:
    created_count: int
    updated_count: int
    errors: list[ImportErrorDetail]
```

Update create-only return to `updated_count=0`.

- [ ] **Step 6: Implement update mode commit**

Change `commit_items_import` signature:

```python
def commit_items_import(result: ItemImportResult, *, import_mode: str = ITEM_IMPORT_MODE_CREATE_ONLY) -> ItemImportCommitResult:
```

Implementation behavior:

- validate with same import mode;
- load units by `unit_code`;
- load existing items by `sku`;
- if create-only: create all rows as now;
- if update-existing: update only rows whose SKU exists, and reject missing SKU rows with `"Артикул не найден для обновления"`;
- do not create new items in update-existing mode.

- [ ] **Step 7: Add form field**

In `ItemImportPreviewForm`, add:

```python
import_mode = forms.ChoiceField(
    label="Режим импорта",
    choices=[
        ("create_only", "Создать только новые позиции"),
        ("update_existing", "Обновить существующие позиции"),
    ],
    initial="create_only",
)
```

- [ ] **Step 8: Wire view**

In `item_import_preview`, read:

```python
import_mode = form.cleaned_data["import_mode"]
```

Pass it to `validate_items_import_result` and `commit_items_import`.

Success messages:

```python
if commit_result.created_count:
    messages.success(request, f"Импортировано позиций: {commit_result.created_count}.")
if commit_result.updated_count:
    messages.success(request, f"Импорт обновил позиций: {commit_result.updated_count}.")
```

- [ ] **Step 9: Update template**

In `templates/warehouse_app/item_import_preview.html`, render `form.import_mode` near `form.workbook`. Add one hint:

```html
<p class="muted">Режим обновления меняет только существующие позиции и не создает новые артикулы.</p>
```

- [ ] **Step 10: Run tests and commit**

```bash
python manage.py test warehouse_app.tests.WarehouseAppTests.test_item_import_create_only_still_rejects_existing_sku warehouse_app.tests.WarehouseAppTests.test_item_import_update_mode_updates_existing_item
python manage.py test
python scripts/check_changed.py --full
python scripts/check_public_readiness.py
git diff --check
git add warehouse_app/imports.py warehouse_app/forms.py warehouse_app/views.py templates/warehouse_app/item_import_preview.html warehouse_app/tests.py docs/releases/v0.4-item-import-update-mode.md
git commit -m "feat: add item import update mode"
```

---

## Task 4: Add Optional Unit Auto-Create Mode For Item Import

**Files:**
- Modify: `warehouse_app/imports.py`
- Modify: `warehouse_app/forms.py`
- Modify: `warehouse_app/views.py`
- Modify: `templates/warehouse_app/item_import_preview.html`
- Modify: `warehouse_app/tests.py`
- Create: `docs/releases/v0.4-item-import-unit-auto-create.md`

**Purpose:** Allow admins to create missing units during item import, but only through an explicit checkbox.

- [ ] **Step 1: Write failing tests**

Add:

```python
    def test_item_import_rejects_unknown_unit_without_auto_create(self):
        admin = User.objects.create_user(username="unit-strict-admin", password="pass")
        UserProfile.objects.create(user=admin, role=UserRole.ADMIN)
        self.client.force_login(admin)

        workbook = self._import_workbook_upload([["AUTO-UNIT-1", "Позиция", "box", "да", ""]])

        response = self.client.post("/items/import/", {"workbook": workbook})

        self.assertContains(response, "Единица не найдена")
        self.assertFalse(Unit.objects.filter(code="box").exists())

    def test_item_import_auto_creates_missing_unit_when_enabled(self):
        admin = User.objects.create_user(username="unit-auto-admin", password="pass")
        UserProfile.objects.create(user=admin, role=UserRole.ADMIN)
        self.client.force_login(admin)

        workbook = self._import_workbook_upload([["AUTO-UNIT-2", "Позиция", "box", "да", ""]])

        response = self.client.post(
            "/items/import/",
            {"action": "commit", "import_mode": "create_only", "auto_create_units": "1", "workbook": workbook},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Unit.objects.filter(code="box", name="box").exists())
        self.assertTrue(Item.objects.filter(sku="AUTO-UNIT-2", unit__code="box").exists())

    def test_item_import_auto_create_units_deduplicates_missing_unit_codes(self):
        admin = User.objects.create_user(username="unit-dedupe-admin", password="pass")
        UserProfile.objects.create(user=admin, role=UserRole.ADMIN)
        self.client.force_login(admin)

        workbook = self._import_workbook_upload(
            [
                ["AUTO-UNIT-3", "Позиция 1", "pack", "да", ""],
                ["AUTO-UNIT-4", "Позиция 2", "pack", "да", ""],
            ]
        )

        response = self.client.post(
            "/items/import/",
            {"action": "commit", "import_mode": "create_only", "auto_create_units": "1", "workbook": workbook},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Unit.objects.filter(code="pack").count(), 1)
        self.assertEqual(Item.objects.filter(unit__code="pack").count(), 2)
```

- [ ] **Step 2: Add explicit option**

Add `auto_create_units: bool = False` parameter to validation and commit functions.

Validation behavior:

- if `auto_create_units=False`, unknown units remain errors;
- if `auto_create_units=True`, unknown units are allowed.

Commit behavior:

- before creating/updating items, create missing `Unit(code=unit_code, name=unit_code)` records inside the same transaction;
- deduplicate missing unit codes with a `set` before creating units, so two imported rows with the same new unit code do not trigger a `Unit.code` uniqueness error;
- never overwrite existing units.

- [ ] **Step 3: Add form checkbox**

In `ItemImportPreviewForm`:

```python
auto_create_units = forms.BooleanField(label="Создать отсутствующие единицы измерения", required=False)
```

- [ ] **Step 4: Wire view and template**

Pass `auto_create_units=form.cleaned_data.get("auto_create_units", False)` to validate/commit. In the template, add a warning:

```html
<p class="muted">Автосоздание единиц использует код как название. Точность можно настроить позже в справочнике единиц.</p>
```

- [ ] **Step 5: Run tests and commit**

```bash
python manage.py test warehouse_app.tests.WarehouseAppTests.test_item_import_rejects_unknown_unit_without_auto_create warehouse_app.tests.WarehouseAppTests.test_item_import_auto_creates_missing_unit_when_enabled warehouse_app.tests.WarehouseAppTests.test_item_import_auto_create_units_deduplicates_missing_unit_codes
python manage.py test
python scripts/check_changed.py --full
python scripts/check_public_readiness.py
git diff --check
git add warehouse_app/imports.py warehouse_app/forms.py warehouse_app/views.py templates/warehouse_app/item_import_preview.html warehouse_app/tests.py docs/releases/v0.4-item-import-unit-auto-create.md
git commit -m "feat: allow explicit unit auto-create during item import"
```

---

## Task 5: Add Item Categories

**Files:**
- Modify: `warehouse_app/models.py`
- Create: `warehouse_app/migrations/0006_itemcategory_item_category.py`
- Modify: `warehouse_app/forms.py`
- Modify: `warehouse_app/admin.py`
- Modify: `warehouse_app/views.py`
- Modify: `warehouse_app/urls.py`
- Create: `templates/warehouse_app/category_list.html`
- Modify: `templates/base.html`
- Modify: `templates/warehouse_app/item_list.html`
- Modify: `warehouse_app/tests.py`
- Create: `docs/releases/v0.4-item-categories.md`

**Purpose:** Add optional item categories for operational filtering without changing stock accounting.

- [ ] **Step 1: Write failing model/form/list tests**

Add:

```python
    def test_item_category_can_be_assigned_to_item(self):
        category = ItemCategory.objects.create(name="Расходники", code="consumables")
        self.item.category = category
        self.item.save()

        self.item.refresh_from_db()
        self.assertEqual(self.item.category, category)

    def test_item_list_filters_by_category(self):
        category = ItemCategory.objects.create(name="Расходники", code="consumables")
        self.item.category = category
        self.item.save()
        other = Item.objects.create(sku="OTHER-CAT", name="Другая позиция", unit=self.unit)

        response = self.client.get("/items/", {"category": str(category.pk)})

        self.assertContains(response, self.item.sku)
        self.assertNotContains(response, other.sku)
```

Add import:

```python
from .models import ItemCategory
```

Expected before implementation: import or attribute failure.

- [ ] **Step 2: Add model**

In `warehouse_app/models.py`, add before `Item`:

```python
class ItemCategory(TimeStampedModel):
    code = models.CharField("Код", max_length=40, unique=True)
    name = models.CharField("Наименование", max_length=120)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Категория номенклатуры"
        verbose_name_plural = "Категории номенклатуры"

    def __str__(self) -> str:
        return self.name
```

Add to `Item`:

```python
category = models.ForeignKey(
    ItemCategory,
    on_delete=models.PROTECT,
    related_name="items",
    verbose_name="Категория",
    null=True,
    blank=True,
)
```

- [ ] **Step 3: Create migration**

Run:

```bash
python manage.py makemigrations warehouse_app
```

Expected migration creates `ItemCategory` and `Item.category`.

- [ ] **Step 4: Add form and admin**

In `forms.py`, create:

```python
class ItemCategoryForm(StyledFieldsMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_field_styles()

    class Meta:
        model = ItemCategory
        fields = ["code", "name", "is_active"]
```

Add `category` to `ItemForm.Meta.fields`.

In `admin.py`, register `ItemCategory`.

- [ ] **Step 5: Add category list/update views**

Add to `views.py`:

```python
@require_reference_manager
def category_list(request: HttpRequest) -> HttpResponse:
    form = ItemCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Категория добавлена.")
        return redirect("category_list")
    categories = ItemCategory.objects.annotate(items_count=Count("items", distinct=True)).order_by("name")
    return render(request, "warehouse_app/category_list.html", {"form": form, "categories": categories})


@require_reference_manager
def category_update(request: HttpRequest, pk: int) -> HttpResponse:
    category = get_object_or_404(ItemCategory, pk=pk)
    form = ItemCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Категория обновлена.")
        return redirect("category_list")
    return render(request, "warehouse_app/simple_form.html", {"form": form, "title": "Редактирование категории", "back_url": reverse("category_list")})
```

- [ ] **Step 6: Add URLs**

In `warehouse_app/urls.py`:

```python
path("categories/", views.category_list, name="category_list"),
path("categories/<int:pk>/edit/", views.category_update, name="category_update"),
```

- [ ] **Step 7: Add category filter to item list**

In `item_list`, read:

```python
category_id = request.GET.get("category")
```

Filter:

```python
if category_id:
    items = items.filter(category_id=category_id)
```

Add context:

```python
"categories": ItemCategory.objects.filter(is_active=True).order_by("name"),
"selected_category": category_id or "",
```

- [ ] **Step 8: Create category template and update navigation**

Create `templates/warehouse_app/category_list.html` using the same two-column layout as unit/warehouse lists. Columns:

- code;
- name;
- active;
- items_count;
- edit link.

Add sidebar link under references:

```html
<a href="{% url 'category_list' %}">Категории</a>
```

- [ ] **Step 9: Run tests and commit**

```bash
python manage.py test warehouse_app.tests.WarehouseAppTests.test_item_category_can_be_assigned_to_item warehouse_app.tests.WarehouseAppTests.test_item_list_filters_by_category
python manage.py test
python scripts/check_changed.py --full
python scripts/check_public_readiness.py
git diff --check
git add warehouse_app/models.py warehouse_app/migrations warehouse_app/forms.py warehouse_app/admin.py warehouse_app/views.py warehouse_app/urls.py templates/base.html templates/warehouse_app/category_list.html templates/warehouse_app/item_list.html warehouse_app/tests.py docs/releases/v0.4-item-categories.md
git commit -m "feat: add item categories"
```

---

## Task 6: Add Category Filters To Operational Reports

**Files:**
- Modify: `warehouse_app/services.py`
- Modify: `warehouse_app/views.py`
- Modify: `templates/warehouse_app/balances.html`
- Modify: `templates/warehouse_app/analytics.html`
- Modify: `templates/warehouse_app/daily_ledger.html`
- Modify: `templates/warehouse_app/monthly_ledger.html`
- Modify: `warehouse_app/tests.py`
- Create: `docs/releases/v0.4-category-report-filters.md`

**Purpose:** Let users filter balances and period reports by item category while keeping current warehouse/date/presentation behavior.

- [ ] **Step 1: Write failing balance filter test**

Add:

```python
    def test_balances_can_filter_by_category(self):
        category = ItemCategory.objects.create(name="Расходники", code="consumables")
        self.item.category = category
        self.item.save()
        other = Item.objects.create(sku="NO-CAT-BAL", name="Без категории", unit=self.unit)
        self._receipt(self.item, "5")
        self._receipt(other, "7")

        response = self.client.get("/balances/", {"category": str(category.pk), "presentation": "consolidated"})

        self.assertContains(response, self.item.sku)
        self.assertNotContains(response, other.sku)
```

- [ ] **Step 2: Add service-level category parameter**

Where balance/report builders accept query filters, add `category_id: str | None = None`. Apply the filter with the correct relation for each queryset type.

```python
if category_id and queryset.model is Item:
    queryset = queryset.filter(category_id=category_id)
elif category_id:
    queryset = queryset.filter(item__category_id=category_id)
```

Use the exact relation name for each queryset:

- item queryset: `category_id`;
- stock line queryset: `item__category_id`;
- inventory line queryset: `item__category_id`.

- [ ] **Step 3: Wire views**

In balances, daily ledger, monthly ledger, and analytics views:

```python
category_id = request.GET.get("category")
```

Pass category to services. Add context:

```python
"categories": ItemCategory.objects.filter(is_active=True).order_by("name"),
"selected_category": category_id or "",
```

Preserve category in export query strings.

- [ ] **Step 4: Add template controls**

Add a category `<select>` to report filter forms:

```html
<select name="category" class="app-control">
    <option value="">Все категории</option>
    {% for category in categories %}
        <option value="{{ category.pk }}"{% if selected_category == category.pk|stringformat:"s" %} selected{% endif %}>{{ category.name }}</option>
    {% endfor %}
</select>
```

- [ ] **Step 5: Add export tests**

Add a test ensuring `/export/balances.xlsx?category=<id>` excludes items from other categories.

- [ ] **Step 6: Run tests and commit**

```bash
python manage.py test warehouse_app.tests.WarehouseAppTests.test_balances_can_filter_by_category
python manage.py test
python scripts/check_changed.py --full
python scripts/check_public_readiness.py
git diff --check
git add warehouse_app/services.py warehouse_app/views.py templates/warehouse_app/balances.html templates/warehouse_app/analytics.html templates/warehouse_app/daily_ledger.html templates/warehouse_app/monthly_ledger.html warehouse_app/tests.py docs/releases/v0.4-category-report-filters.md
git commit -m "feat: add category filters to reports"
```

---

## Task 7: Add User Saved Views

**Files:**
- Modify: `warehouse_app/models.py`
- Create: `warehouse_app/migrations/0007_usersavedview.py`
- Modify: `warehouse_app/forms.py`
- Modify: `warehouse_app/views.py`
- Modify: `warehouse_app/urls.py`
- Modify: `templates/warehouse_app/document_list.html`
- Modify: `templates/warehouse_app/balances.html`
- Modify: `warehouse_app/tests.py`
- Create: `docs/releases/v0.4-user-saved-views.md`

**Purpose:** Allow authenticated users to save frequently used document and balance filter sets. Anonymous demo/local users continue using built-in presets only.

- [ ] **Step 1: Add model**

In `models.py`:

```python
class SavedViewScope(models.TextChoices):
    DOCUMENTS = "documents", "Документы движения"
    BALANCES = "balances", "Текущие остатки"


class UserSavedView(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="warehouse_saved_views")
    scope = models.CharField("Раздел", max_length=20, choices=SavedViewScope.choices)
    name = models.CharField("Название", max_length=80)
    query_params = models.JSONField("Параметры")
    is_default = models.BooleanField("По умолчанию", default=False)

    class Meta:
        ordering = ["scope", "name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "scope", "name"], name="unique_saved_view_name_per_user_scope")
        ]
```

- [ ] **Step 2: Create migration**

```bash
python manage.py makemigrations warehouse_app
```

- [ ] **Step 3: Write tests**

Add:

```python
    def test_authenticated_user_can_save_document_view(self):
        user = User.objects.create_user(username="saved-view-user", password="pass")
        UserProfile.objects.create(user=user, role=UserRole.OPERATOR)
        self.client.force_login(user)

        response = self.client.post(
            "/saved-views/documents/create/",
            {"name": "Мои черновики", "status": DocumentStatus.DRAFT, "warehouse": str(self.warehouse.pk)},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        saved = UserSavedView.objects.get(user=user, scope="documents")
        self.assertEqual(saved.name, "Мои черновики")
        self.assertEqual(saved.query_params["status"], DocumentStatus.DRAFT)
```

Add:

```python
    def test_anonymous_user_cannot_save_view(self):
        response = self.client.post("/saved-views/documents/create/", {"name": "Test"})

        self.assertEqual(response.status_code, 302)
```

- [ ] **Step 4: Add save view endpoints**

In `urls.py`:

```python
path("saved-views/<str:scope>/create/", views.saved_view_create, name="saved_view_create"),
path("saved-views/<int:pk>/delete/", views.saved_view_delete, name="saved_view_delete"),
```

In `views.py`, implement:

```python
@require_POST
def saved_view_create(request: HttpRequest, scope: str) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("login")
    if scope not in {"documents", "balances"}:
        raise PermissionDenied("Unknown saved view scope.")
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Укажите название представления.")
        return redirect("document_list" if scope == "documents" else "balance_report")
    allowed_keys = {
        "documents": {"q", "warehouse", "document_type", "status", "date_from", "date_to", "preset", "category"},
        "balances": {"q", "warehouse", "presentation", "include_zero", "preset", "category"},
    }[scope]
    query_params = {key: request.POST.get(key, "") for key in allowed_keys if key in request.POST}
    UserSavedView.objects.update_or_create(
        user=request.user,
        scope=scope,
        name=name,
        defaults={"query_params": query_params},
    )
    messages.success(request, "Представление сохранено.")
    return redirect("document_list" if scope == "documents" else "balance_report")


@require_POST
def saved_view_delete(request: HttpRequest, pk: int) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("login")
    saved_view = get_object_or_404(UserSavedView, pk=pk, user=request.user)
    scope = saved_view.scope
    saved_view.delete()
    messages.success(request, "Представление удалено.")
    return redirect("document_list" if scope == "documents" else "balance_report")
```

- [ ] **Step 5: Render saved views**

In document and balance list views, add:

```python
"saved_views": UserSavedView.objects.filter(user=request.user, scope="documents") if request.user.is_authenticated else [],
```

In templates, render small links:

```html
{% for saved_view in saved_views %}
    <a class="chip" href="?{{ saved_view.query_params|urlencode_dict }}">{{ saved_view.name }}</a>
{% endfor %}
```

If no `urlencode_dict` exists, add a template filter in `warehouse_app/templatetags/warehouse_tags.py` using `urllib.parse.urlencode`.

- [ ] **Step 6: Run tests and commit**

```bash
python manage.py test warehouse_app.tests.WarehouseAppTests.test_authenticated_user_can_save_document_view warehouse_app.tests.WarehouseAppTests.test_anonymous_user_cannot_save_view
python manage.py test
python scripts/check_changed.py --full
python scripts/check_public_readiness.py
git diff --check
git add warehouse_app/models.py warehouse_app/migrations warehouse_app/forms.py warehouse_app/views.py warehouse_app/urls.py templates/warehouse_app/document_list.html templates/warehouse_app/balances.html warehouse_app/templatetags/warehouse_tags.py warehouse_app/tests.py docs/releases/v0.4-user-saved-views.md
git commit -m "feat: add user saved views"
```

---

## Task 8: Close v0.4.0 Stage B

**Files:**
- Modify: `warehouse_app/version.py`
- Modify: `desktop/electron_shell/package.json`
- Modify: `docs/STATUS.md`
- Modify: `docs/TECH_SPEC.md`
- Create: `docs/releases/v0.4.0-stage-b-closure.md`

- [ ] **Step 1: Bump version**

Set:

```python
APP_VERSION = "0.4.0"
```

Set Electron package version:

```json
"version": "0.4.0"
```

- [ ] **Step 2: Add closure release note**

Create `docs/releases/v0.4.0-stage-b-closure.md`:

```markdown
# v0.4.0 Stage B Closure

Date: 2026-06-04

## Purpose

Close Stage B operational contour work.

## Included Slices

- Stage B scope reconciliation.
- Import column aliases.
- Item import update mode.
- Explicit unit auto-create mode.
- Item categories.
- Category-aware operational filters.
- User saved views.

## Do Not Regress

Preserve `v0.1 MVP Baseline` and `v0.3.0 Stage A Closure` invariants.
```

- [ ] **Step 3: Run full verification**

```bash
python manage.py check
python manage.py test
python scripts/check_changed.py --full
python scripts/check_public_readiness.py
python -m unittest discover -s scripts -p 'test_check_public_readiness.py'
git diff --check
```

Expected:

```text
System check identified no issues
Ran 111+ tests
OK
Public readiness check passed
```

- [ ] **Step 4: Commit**

```bash
git add warehouse_app/version.py desktop/electron_shell/package.json docs/STATUS.md docs/TECH_SPEC.md docs/releases/v0.4.0-stage-b-closure.md
git commit -m "release: mark v0.4.0 stage b closure"
```

---

## Self-Review

### Spec Coverage

- Stage B scope reconciliation: Task 1.
- Flexible import columns: Task 2.
- Existing item update mode: Task 3.
- Unit auto-create mode: Task 4.
- Categories: Task 5.
- Report filters by category: Task 6.
- Saved views: Task 7.
- Version closure: Task 8.

### Known Deferrals

- Production-grade RBAC remains deferred until pilot feedback.
- Object-level permissions remain deferred.
- Desktop packaging remains separate from Stage B.
- Client-side index remains a later trial and is not part of this operational contour plan.

### Risk Controls

- Every import enhancement keeps preview/validation before commit.
- Opening stock import still creates inventory drafts, never direct balance writes.
- Categories are optional and must not affect stock posting.
- Saved views store only query params, not result snapshots.
- Existing built-in presets remain available for anonymous/demo users.

### Verification Standard

Every PR from this plan must run:

```bash
python manage.py check
python manage.py test
python scripts/check_changed.py --full
python scripts/check_public_readiness.py
git diff --check
```

Use browser smoke testing for any PR that changes visible forms, filters, or navigation.
