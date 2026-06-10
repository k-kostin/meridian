# User Attribution Implementation Plan

> **For agentic workers:** Implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pilot-grade user attribution for core warehouse operations: who created, last updated, and posted stock documents and inventory documents, and who appears as actor in their activity timeline events.

**Architecture:** Keep attribution explicit and local to operational records. Add nullable user foreign keys to `StockDocument`, `InventoryDocument`, and `ActivityEvent`; pass the current request user from views into create/update/post flows; keep anonymous local/demo mode supported by leaving attribution empty when no authenticated user exists.

**Tech Stack:** Django 6, SQLite, Django ORM migrations, server-rendered templates, existing role helpers and activity timeline.

---

## Scope And Non-Goals

In scope:

- `created_by`, `updated_by`, `posted_by` for `StockDocument`;
- `created_by`, `updated_by`, `posted_by` for `InventoryDocument`;
- `actor` and `actor_label` for `ActivityEvent`;
- views pass `request.user` into create/update/post flows;
- detail pages show created/updated/posted users;
- activity timelines show event actor;
- tests for authenticated admin/operator attribution and anonymous local compatibility.

Out of scope for this slice:

- attribution for every reference edit;
- attribution for item import commit;
- attribution for opening inventory import commit beyond the created inventory document fields;
- demo reload audit event;
- immutable security-grade audit log;
- object-level permissions.

Those out-of-scope items belong to the later audit-hardening slice.

## File Structure

- Modify `warehouse_app/models.py`
  - Add attribution fields to `StockDocument`, `InventoryDocument`, and `ActivityEvent`.
  - Update `StockDocument.post()` and `InventoryDocument.post()` signatures to accept `posted_by=None`.
- Create `warehouse_app/migrations/0009_user_attribution.py`
  - Adds nullable attribution fields.
- Modify `warehouse_app/activity.py`
  - Accept `actor=None` in event recording functions.
  - Store `actor` FK and stable `actor_label`.
  - Select related actor in timeline queries.
- Modify `warehouse_app/views.py`
  - Set `created_by` and `updated_by` on document/inventory create/update.
  - Pass `posted_by=request.user` to post methods.
- Modify `templates/warehouse_app/document_detail.html`
  - Show created/updated/posted users in document metadata.
- Modify `templates/warehouse_app/inventory_detail.html`
  - Show created/updated/posted users in inventory metadata.
- Modify `templates/warehouse_app/includes/activity_timeline.html`
  - Show event actor label when present.
- Modify `warehouse_app/tests.py`
  - Add focused tests for attribution behavior.
- Modify `docs/TECH_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/ROADMAP.md`
  - Mark core operation attribution as implemented and document remaining audit gaps.

## Attribution Rules

- Authenticated user:
  - create stock document -> `created_by` and `updated_by`;
  - edit draft stock document -> `updated_by`;
  - post stock document -> `posted_by`, `updated_by`, and activity `actor`;
  - create inventory -> `created_by` and `updated_by`;
  - edit draft inventory -> `updated_by`;
  - post inventory -> `posted_by`, `updated_by`, and activity `actor`.
- Anonymous local/demo user:
  - attribution fields remain `NULL`;
  - existing anonymous MVP/demo behavior stays working.
- `actor_label`:
  - for authenticated users, store `user.get_username()`;
  - for anonymous or missing actor, store empty string;
  - keep it as a stable label even if the FK is later null.

---

### Task 1: Add Attribution Fields To Models

**Files:**
- Modify: `warehouse_app/models.py`
- Create: `warehouse_app/migrations/0009_user_attribution.py`
- Test: `warehouse_app/tests.py`

- [ ] **Step 1: Write failing model tests**

Append this test class near other focused model tests in `warehouse_app/tests.py`:

```python
class UserAttributionModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="operator", password="pass")
        self.unit = Unit.objects.create(code="pcs", name="Штука")
        self.warehouse = Warehouse.objects.create(code="main", name="Основной склад")
        self.item = Item.objects.create(sku="SKU-1", name="Позиция", unit=self.unit)

    def test_stock_document_stores_created_updated_and_posted_users(self):
        document = StockDocument.objects.create(
            document_type=StockDocumentType.RECEIPT,
            warehouse=self.warehouse,
            operation_date=date(2026, 6, 10),
            created_by=self.user,
            updated_by=self.user,
        )
        StockDocumentLine.objects.create(document=document, item=self.item, quantity=Decimal("2"))

        document.post(posted_by=self.user)
        document.refresh_from_db()

        self.assertEqual(document.created_by, self.user)
        self.assertEqual(document.updated_by, self.user)
        self.assertEqual(document.posted_by, self.user)

    def test_inventory_document_stores_created_updated_and_posted_users(self):
        inventory = InventoryDocument.objects.create(
            warehouse=self.warehouse,
            inventory_date=date(2026, 6, 10),
            scope=InventoryScope.FULL,
            created_by=self.user,
            updated_by=self.user,
        )
        InventoryLine.objects.create(
            inventory=inventory,
            item=self.item,
            expected_quantity=Decimal("0"),
            actual_quantity=Decimal("1"),
        )

        inventory.post(posted_by=self.user)
        inventory.refresh_from_db()

        self.assertEqual(inventory.created_by, self.user)
        self.assertEqual(inventory.updated_by, self.user)
        self.assertEqual(inventory.posted_by, self.user)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python manage.py test warehouse_app.tests.UserAttributionModelTests
```

Expected: FAIL because attribution fields and `posted_by` method parameters do not exist.

- [ ] **Step 3: Add model fields**

In `warehouse_app/models.py`, add this helper near other small helpers:

```python
def attribution_user_field(related_name: str):
    return models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name=related_name,
        verbose_name="Пользователь",
        null=True,
        blank=True,
    )
```

Add to `StockDocument`:

```python
    created_by = attribution_user_field("created_stock_documents")
    updated_by = attribution_user_field("updated_stock_documents")
    posted_by = attribution_user_field("posted_stock_documents")
```

Add to `InventoryDocument`:

```python
    created_by = attribution_user_field("created_inventory_documents")
    updated_by = attribution_user_field("updated_inventory_documents")
    posted_by = attribution_user_field("posted_inventory_documents")
```

Add to `ActivityEvent`:

```python
    actor = attribution_user_field("warehouse_activity_events")
    actor_label = models.CharField("Пользователь", max_length=150, blank=True)
```

- [ ] **Step 4: Update post method signatures**

Change `StockDocument.post()` signature:

```python
    def post(self, *, posted_by=None):
```

Inside the successful post branch, before saving `locked_document`, set:

```python
        if getattr(posted_by, "is_authenticated", False):
            locked_document.posted_by = posted_by
            locked_document.updated_by = posted_by
```

Change the event call:

```python
        record_stock_document_posted(locked_document, actor=posted_by)
```

Change `InventoryDocument.post()` signature:

```python
    def post(self, *, posted_by=None):
```

When posting generated adjustment, pass:

```python
            adjustment.post(posted_by=posted_by)
```

Before saving `locked_inventory`, set:

```python
        if getattr(posted_by, "is_authenticated", False):
            locked_inventory.posted_by = posted_by
            locked_inventory.updated_by = posted_by
```

Change event calls:

```python
        record_inventory_posted(locked_inventory, actor=posted_by)
        if adjustment:
            record_inventory_adjustment_created(locked_inventory, adjustment, actor=posted_by)
```

- [ ] **Step 5: Create migration**

Run:

```bash
python manage.py makemigrations warehouse_app
```

Expected: creates `warehouse_app/migrations/0009_user_attribution.py`.

- [ ] **Step 6: Run model tests**

Run:

```bash
python manage.py test warehouse_app.tests.UserAttributionModelTests
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add warehouse_app/models.py warehouse_app/migrations/0009_user_attribution.py warehouse_app/tests.py
git commit -m "feat: add operation attribution fields"
```

---

### Task 2: Add Actor To Activity Events

**Files:**
- Modify: `warehouse_app/activity.py`
- Modify: `warehouse_app/tests.py`

- [ ] **Step 1: Write failing activity tests**

Append to `UserAttributionModelTests`:

```python
    def test_stock_document_posted_event_stores_actor(self):
        document = StockDocument.objects.create(
            document_type=StockDocumentType.RECEIPT,
            warehouse=self.warehouse,
            operation_date=date(2026, 6, 10),
        )
        StockDocumentLine.objects.create(document=document, item=self.item, quantity=Decimal("2"))

        document.post(posted_by=self.user)

        event = ActivityEvent.objects.get(stock_document=document, event_type=ActivityEventType.STOCK_DOCUMENT_POSTED)
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.actor_label, "operator")

    def test_inventory_posted_events_store_actor(self):
        inventory = InventoryDocument.objects.create(
            warehouse=self.warehouse,
            inventory_date=date(2026, 6, 10),
            scope=InventoryScope.FULL,
        )
        InventoryLine.objects.create(
            inventory=inventory,
            item=self.item,
            expected_quantity=Decimal("0"),
            actual_quantity=Decimal("1"),
        )

        inventory.post(posted_by=self.user)

        events = ActivityEvent.objects.filter(inventory_document=inventory)
        self.assertTrue(events.filter(actor=self.user, actor_label="operator").exists())
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python manage.py test warehouse_app.tests.UserAttributionModelTests
```

Expected: FAIL because activity functions do not pass actor.

- [ ] **Step 3: Implement activity actor helpers**

In `warehouse_app/activity.py`, add:

```python
def actor_defaults(actor) -> dict:
    if getattr(actor, "is_authenticated", False):
        return {"actor": actor, "actor_label": actor.get_username()}
    return {"actor": None, "actor_label": ""}
```

Change function signatures:

```python
def record_stock_document_posted(document: StockDocument, *, actor=None) -> None:
def record_inventory_posted(inventory: InventoryDocument, *, actor=None) -> None:
def record_inventory_adjustment_created(inventory: InventoryDocument, adjustment: StockDocument, *, actor=None) -> None:
```

In each `defaults={...}` dict, merge:

```python
            **actor_defaults(actor),
```

Update timeline queries:

```python
    return ActivityEvent.objects.select_related("warehouse", "actor").filter(stock_document=document)
```

```python
    return ActivityEvent.objects.select_related("warehouse", "actor").filter(inventory_document=inventory)
```

- [ ] **Step 4: Run activity tests**

Run:

```bash
python manage.py test warehouse_app.tests.UserAttributionModelTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add warehouse_app/activity.py warehouse_app/tests.py
git commit -m "feat: attribute activity events to users"
```

---

### Task 3: Wire Attribution In Views

**Files:**
- Modify: `warehouse_app/views.py`
- Modify: `warehouse_app/tests.py`

- [ ] **Step 1: Write failing view tests**

Add a new test class:

```python
class UserAttributionViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="operator", password="pass")
        UserProfile.objects.create(user=self.user, role=UserRole.OPERATOR)
        self.unit = Unit.objects.create(code="pcs", name="Штука")
        self.warehouse = Warehouse.objects.create(code="main", name="Основной склад")
        self.item = Item.objects.create(sku="SKU-1", name="Позиция", unit=self.unit)
        self.client.force_login(self.user)

    def test_document_create_sets_created_and_updated_by(self):
        response = self.client.post(
            "/documents/new/?type=receipt",
            {
                "document_type": StockDocumentType.RECEIPT,
                "warehouse": self.warehouse.pk,
                "destination_warehouse": "",
                "operation_date": "2026-06-10",
                "comment": "",
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-item": self.item.pk,
                "lines-0-quantity": "2",
                "lines-0-comment": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        document = StockDocument.objects.get()
        self.assertEqual(document.created_by, self.user)
        self.assertEqual(document.updated_by, self.user)

    def test_document_post_sets_posted_by(self):
        document = StockDocument.objects.create(
            document_type=StockDocumentType.RECEIPT,
            warehouse=self.warehouse,
            operation_date=date(2026, 6, 10),
        )
        StockDocumentLine.objects.create(document=document, item=self.item, quantity=Decimal("2"))

        response = self.client.post(f"/documents/{document.pk}/post/")

        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertEqual(document.posted_by, self.user)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python manage.py test warehouse_app.tests.UserAttributionViewTests
```

Expected: FAIL because views do not set attribution fields.

- [ ] **Step 3: Add request user helper**

In `warehouse_app/views.py`, add near helper functions:

```python
def authenticated_actor(request: HttpRequest):
    return request.user if request.user.is_authenticated else None
```

- [ ] **Step 4: Set document create/update attribution**

In `document_create`, after `document = form.save(commit=False)` and before saving:

```python
                actor = authenticated_actor(request)
                if actor:
                    document.created_by = actor
                    document.updated_by = actor
```

In `document_update`, after `document = form.save(commit=False)` and before saving:

```python
                actor = authenticated_actor(request)
                if actor:
                    document.updated_by = actor
```

If current code calls `form.save()` directly, change it to `form.save(commit=False)`, set fields, then `document.save()`.

- [ ] **Step 5: Pass actor to document posting**

In `document_post`:

```python
        document.post(posted_by=authenticated_actor(request))
```

- [ ] **Step 6: Set inventory create/update/post attribution**

In `inventory_create`, set `created_by` and `updated_by` the same way before saving.

In `inventory_update`, set `updated_by` before saving.

In `inventory_post`:

```python
        inventory.post(posted_by=authenticated_actor(request))
```

- [ ] **Step 7: Run view tests**

Run:

```bash
python manage.py test warehouse_app.tests.UserAttributionViewTests
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add warehouse_app/views.py warehouse_app/tests.py
git commit -m "feat: set operation attribution from views"
```

---

### Task 4: Show Attribution In UI

**Files:**
- Modify: `templates/warehouse_app/document_detail.html`
- Modify: `templates/warehouse_app/inventory_detail.html`
- Modify: `templates/warehouse_app/includes/activity_timeline.html`
- Modify: `warehouse_app/tests.py`

- [ ] **Step 1: Write failing UI tests**

Append to `UserAttributionViewTests`:

```python
    def test_document_detail_shows_posted_by_user(self):
        document = StockDocument.objects.create(
            document_type=StockDocumentType.RECEIPT,
            warehouse=self.warehouse,
            operation_date=date(2026, 6, 10),
            created_by=self.user,
            updated_by=self.user,
        )
        StockDocumentLine.objects.create(document=document, item=self.item, quantity=Decimal("2"))
        document.post(posted_by=self.user)

        response = self.client.get(f"/documents/{document.pk}/")

        self.assertContains(response, "Провел")
        self.assertContains(response, "operator")

    def test_inventory_detail_shows_posted_by_user(self):
        inventory = InventoryDocument.objects.create(
            warehouse=self.warehouse,
            inventory_date=date(2026, 6, 10),
            scope=InventoryScope.FULL,
            created_by=self.user,
            updated_by=self.user,
        )
        InventoryLine.objects.create(
            inventory=inventory,
            item=self.item,
            expected_quantity=Decimal("0"),
            actual_quantity=Decimal("1"),
        )
        inventory.post(posted_by=self.user)

        response = self.client.get(f"/inventories/{inventory.pk}/")

        self.assertContains(response, "Провел")
        self.assertContains(response, "operator")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python manage.py test warehouse_app.tests.UserAttributionViewTests
```

Expected: FAIL because templates do not display attribution.

- [ ] **Step 3: Update document detail template**

In `templates/warehouse_app/document_detail.html`, add metadata rows where document status/date/warehouse are shown:

```html
<dt>Создал</dt>
<dd>{{ document.created_by|default:"-" }}</dd>
<dt>Обновил</dt>
<dd>{{ document.updated_by|default:"-" }}</dd>
<dt>Провел</dt>
<dd>{{ document.posted_by|default:"-" }}</dd>
```

- [ ] **Step 4: Update inventory detail template**

In `templates/warehouse_app/inventory_detail.html`, add:

```html
<dt>Создал</dt>
<dd>{{ inventory.created_by|default:"-" }}</dd>
<dt>Обновил</dt>
<dd>{{ inventory.updated_by|default:"-" }}</dd>
<dt>Провел</dt>
<dd>{{ inventory.posted_by|default:"-" }}</dd>
```

- [ ] **Step 5: Update timeline template**

In `templates/warehouse_app/includes/activity_timeline.html`, inside each event row/card, add:

```html
{% if event.actor_label %}
    <span class="muted">Пользователь: {{ event.actor_label }}</span>
{% endif %}
```

Place it near event timestamp/message so it is visible without opening another page.

- [ ] **Step 6: Run UI tests**

Run:

```bash
python manage.py test warehouse_app.tests.UserAttributionViewTests
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add templates/warehouse_app/document_detail.html templates/warehouse_app/inventory_detail.html templates/warehouse_app/includes/activity_timeline.html warehouse_app/tests.py
git commit -m "feat: show operation attribution in UI"
```

---

### Task 5: Update Docs And Verify

**Files:**
- Modify: `docs/TECH_SPEC.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update TECH_SPEC**

Add near existing attribution requirement:

```markdown
- Core operation user attribution must record creator, last updater, and poster for stock documents and inventory documents.
- Activity timeline events for posting must show the actor when the action came from an authenticated user.
```

- [ ] **Step 2: Update ARCHITECTURE**

Add under domain invariants:

```markdown
- User attribution is pilot-grade operational metadata, not a security-grade immutable audit log.
- Anonymous local/demo flows keep attribution nullable to preserve single-computer demo compatibility.
```

- [ ] **Step 3: Update STATUS**

Move the limitation:

```markdown
- core operation attribution exists for stock documents, inventory documents, and their posting events;
- import/demo/reference-edit attribution remains future audit-hardening work.
```

- [ ] **Step 4: Update ROADMAP**

Under Stage C `User attribution`, mark first slice:

```markdown
First slice implemented: creator/updater/poster fields for stock documents and inventory documents, plus actor on posting timeline events. Import/demo/reference attribution remains for audit hardening.
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
python manage.py test warehouse_app.tests.UserAttributionModelTests warehouse_app.tests.UserAttributionViewTests
```

Expected: PASS.

- [ ] **Step 6: Run full verification**

Run:

```bash
python manage.py test
python manage.py check
python scripts/check_public_readiness.py
git diff --check
```

Expected: all pass. If `scripts/check_public_readiness.py` reports generated `db.sqlite3` or `__pycache__`, remove generated artifacts and rerun it:

```bash
rm -rf db.sqlite3 backups config/__pycache__ warehouse_app/__pycache__ warehouse_app/templatetags/__pycache__ warehouse_app/migrations/__pycache__ warehouse_app/management/__pycache__ warehouse_app/management/commands/__pycache__
python scripts/check_public_readiness.py
```

- [ ] **Step 7: Browser smoke**

Run:

```bash
WAREHOUSE_DEMO_MODE=1 DJANGO_DEBUG=1 python manage.py runserver 127.0.0.1:8000 --noreload
```

Verify:

- create a draft document while logged in or as an authenticated operator test user;
- post it;
- detail page shows `Создал`, `Обновил`, `Провел`;
- timeline shows actor label;
- anonymous demo/local mode still opens document create without attribution errors.

- [ ] **Step 8: Commit**

```bash
git add docs/TECH_SPEC.md docs/ARCHITECTURE.md docs/STATUS.md docs/ROADMAP.md
git commit -m "docs: document operation user attribution"
```

---

### Task 6: PR And Review

**Files:**
- No new files.

- [ ] **Step 1: Inspect branch**

Run:

```bash
git status --short
git log --oneline --max-count=8
```

Expected: clean working tree and only intended attribution commits on the branch.

- [ ] **Step 2: Push and create PR**

Run:

```bash
git push -u origin stage-c-user-attribution
gh pr create --title "Add core operation user attribution" --body "## Summary
- add creator/updater/poster attribution to stock documents and inventory documents
- attribute posting timeline events to authenticated users
- show attribution on detail pages and timelines
- document remaining audit-hardening gaps

## Verification
- python manage.py test
- python manage.py check
- python scripts/check_public_readiness.py
- git diff --check
- browser smoke for document/inventory detail attribution"
```

- [ ] **Step 3: Inspect review comments**

Run:

```bash
gh pr view --json comments,reviews,reviewDecision
gh api repos/k-kostin/meridian/pulls/<PR_NUMBER>/comments
gh api repos/k-kostin/meridian/issues/<PR_NUMBER>/comments
```

If review comments identify real regressions, fix them on the same branch, rerun targeted tests plus public-readiness, push, and recheck comments.

---

## Self-Review

Spec coverage:

- Creator/updater/poster for documents: Task 1 and Task 3.
- Creator/updater/poster for inventories: Task 1 and Task 3.
- Actor on posting timeline events: Task 2 and Task 4.
- Anonymous local compatibility: Task 3 and verification.
- Audit-hardening boundaries: Task 5.

Placeholder scan:

- No open-ended implementation placeholders.
- Code steps contain concrete snippets and commands.

Type consistency:

- Field names are consistent: `created_by`, `updated_by`, `posted_by`, `actor`, `actor_label`.
- Method parameters are consistent: `posted_by=None`.
- Template labels are consistent: `Создал`, `Обновил`, `Провел`.

