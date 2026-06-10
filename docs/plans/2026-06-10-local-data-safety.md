# Local Data Safety Implementation Plan

> **For agentic workers:** Implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Stage C `Local Single User` data-safety slice: SQLite backups, restore procedure, pre-migration backup hook, UI visibility, and documentation.

**Architecture:** Keep data safety outside domain stock-accounting rules. Add a small backup service around the configured SQLite database path, persist backup metadata in `BackupRecord`, expose manual backup/download/list in the web UI for admins, and keep restore as a management command because replacing the active SQLite database from a running web request is unsafe.

**Tech Stack:** Django 6, SQLite, Python standard library `sqlite3`, `hashlib`, `shutil`, `pathlib`, Django management commands, server-rendered templates.

---

## Scope And Non-Goals

This plan implements the first safe slice only.

In scope:

- backup metadata model;
- manual local backup service;
- admin-only backup list/create/download UI;
- restore management command with mandatory confirmation;
- pre-migration backup call in the desktop sidecar before `migrate`;
- docs/spec/status updates;
- tests for service, permissions, command behavior, and UI routes.

Out of scope:

- web restore button;
- cloud backup;
- automatic scheduled backup;
- encrypted backup;
- multi-user PostgreSQL backup strategy;
- user-attribution expansion for all stock actions.

## File Structure

- Create `warehouse_app/backups.py`
  - Owns local SQLite backup/restore primitives and metadata helpers.
  - Does not import views and does not know about HTTP.
- Modify `warehouse_app/models.py`
  - Adds `BackupRecord`.
- Create `warehouse_app/migrations/0013_backuprecord.py`
  - Adds backup metadata table.
- Modify `warehouse_app/permissions.py`
  - Adds explicit `can_manage_backups()` and `require_backup_manager()`.
- Modify `warehouse_app/views.py`
  - Adds backup list, create, and download views.
- Modify `warehouse_app/urls.py`
  - Adds `/backups/`, `/backups/create/`, `/backups/<pk>/download/`.
- Create `templates/warehouse_app/backup_list.html`
  - Shows data-dir, database path label, backup records, create/download actions.
- Modify `templates/base.html`
  - Adds a navigation link under an operational/admin group.
- Create `warehouse_app/management/commands/create_local_backup.py`
  - CLI backup command.
- Create `warehouse_app/management/commands/restore_local_backup.py`
  - CLI restore command with required `--confirm`.
- Modify `desktop/python_sidecar/serve.py`
  - Creates pre-migration backup if an existing SQLite database is present.
- Modify `warehouse_app/tests.py`
  - Adds focused tests without splitting the current test file.
- Modify `docs/TECH_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/ROADMAP.md`, `docs/DESKTOP_APP.md`
  - Documents Local Single User data-safety behavior and limitations.

## Naming Decisions

- Public UI label: `Резервные копии`.
- Model: `BackupRecord`.
- Service module: `warehouse_app.backups`.
- Backup kind values:
  - `manual`
  - `pre_migration`
  - `pre_restore`
- Backup status values:
  - `created`
  - `failed`
  - `restored`

## Backup File Format

Use plain SQLite file copies created through the SQLite backup API.

Filename:

```text
meridian-YYYYMMDD-HHMMSS-<kind>.sqlite3
```

Metadata fields:

- kind;
- status;
- backup path;
- source database path;
- size in bytes;
- SHA-256;
- app version;
- message;
- JSON metadata;
- optional user.

---

### Task 1: Add BackupRecord Model

**Files:**
- Modify: `warehouse_app/models.py`
- Create: `warehouse_app/migrations/0013_backuprecord.py`
- Test: `warehouse_app/tests.py`

- [ ] **Step 1: Write the failing model test**

Append this test class near the existing model-level tests in `warehouse_app/tests.py`:

```python
class BackupRecordModelTests(TestCase):
    def test_backup_record_string_contains_kind_and_status(self):
        record = BackupRecord.objects.create(
            kind=BackupKind.MANUAL,
            status=BackupStatus.CREATED,
            backup_path="/tmp/meridian-20260610-120000-manual.sqlite3",
            source_database_path="/tmp/db.sqlite3",
            size_bytes=128,
            sha256="a" * 64,
            app_version="v0.5.0-dev",
        )

        self.assertIn("manual", str(record))
        self.assertIn("created", str(record))
```

Add these imports at the top of `warehouse_app/tests.py`:

```python
from warehouse_app.models import BackupKind, BackupRecord, BackupStatus
```

If `warehouse_app/tests.py` already imports many model symbols in a parenthesized import, add the three names to that existing import instead of creating a second import.

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python manage.py test warehouse_app.tests.BackupRecordModelTests
```

Expected: FAIL because `BackupRecord`, `BackupKind`, and `BackupStatus` do not exist.

- [ ] **Step 3: Add model code**

Add this code to `warehouse_app/models.py` after `UserProfile` and before stock document models:

```python
class BackupKind(models.TextChoices):
    MANUAL = "manual", "Ручная"
    PRE_MIGRATION = "pre_migration", "Перед миграцией"
    PRE_RESTORE = "pre_restore", "Перед восстановлением"


class BackupStatus(models.TextChoices):
    CREATED = "created", "Создана"
    FAILED = "failed", "Ошибка"
    RESTORED = "restored", "Восстановлена"


class BackupRecord(TimeStampedModel):
    kind = models.CharField("Тип", max_length=32, choices=BackupKind.choices)
    status = models.CharField("Статус", max_length=32, choices=BackupStatus.choices)
    backup_path = models.CharField("Путь к копии", max_length=500)
    source_database_path = models.CharField("Путь к базе", max_length=500)
    size_bytes = models.PositiveBigIntegerField("Размер, байт", default=0)
    sha256 = models.CharField("SHA-256", max_length=64, blank=True)
    app_version = models.CharField("Версия приложения", max_length=32, blank=True)
    message = models.CharField("Сообщение", max_length=255, blank=True)
    metadata = models.JSONField("Метаданные", default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="backup_records",
        verbose_name="Пользователь",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Резервная копия"
        verbose_name_plural = "Резервные копии"

    def __str__(self) -> str:
        return f"{self.kind} / {self.status} / {self.created_at:%Y-%m-%d %H:%M:%S}"
```

Add this import near the top of `warehouse_app/models.py` if it is not already present:

```python
from django.conf import settings
```

- [ ] **Step 4: Create migration**

Run:

```bash
python manage.py makemigrations warehouse_app
```

Expected: creates a migration similar to `warehouse_app/migrations/0013_backuprecord.py`.

Open the migration and verify it only creates `BackupRecord` and does not alter stock-accounting models.

- [ ] **Step 5: Run the model test**

Run:

```bash
python manage.py test warehouse_app.tests.BackupRecordModelTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add warehouse_app/models.py warehouse_app/migrations/0013_backuprecord.py warehouse_app/tests.py
git commit -m "feat: add backup record model"
```

---

### Task 2: Add Local SQLite Backup Service

**Files:**
- Create: `warehouse_app/backups.py`
- Modify: `warehouse_app/tests.py`

- [ ] **Step 1: Write failing service tests**

Append this test class to `warehouse_app/tests.py`:

```python
class LocalBackupServiceTests(TestCase):
    def test_create_local_backup_copies_sqlite_database_and_records_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "db.sqlite3"
            backup_dir = temp_path / "backups"

            with sqlite3.connect(db_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
                connection.execute("INSERT INTO sample (name) VALUES ('alpha')")
                connection.commit()

            record = create_local_backup(
                database_path=db_path,
                backup_dir=backup_dir,
                kind=BackupKind.MANUAL,
                app_version="v0.5.0-dev",
                message="Manual backup created.",
            )

            self.assertEqual(record.status, BackupStatus.CREATED)
            self.assertEqual(record.kind, BackupKind.MANUAL)
            self.assertTrue(Path(record.backup_path).exists())
            self.assertGreater(record.size_bytes, 0)
            self.assertEqual(len(record.sha256), 64)

            with sqlite3.connect(record.backup_path) as backup_connection:
                rows = list(backup_connection.execute("SELECT name FROM sample"))

            self.assertEqual(rows, [("alpha",)])

    def test_create_local_backup_fails_for_missing_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            with self.assertRaises(BackupError):
                create_local_backup(
                    database_path=temp_path / "missing.sqlite3",
                    backup_dir=temp_path / "backups",
                    kind=BackupKind.MANUAL,
                    app_version="v0.5.0-dev",
                )
```

Add imports:

```python
import sqlite3
import tempfile
from pathlib import Path

from warehouse_app.backups import BackupError, create_local_backup
```

If the stdlib imports already exist, reuse them.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python manage.py test warehouse_app.tests.LocalBackupServiceTests
```

Expected: FAIL because `warehouse_app.backups` does not exist.

- [ ] **Step 3: Implement backup service**

Create `warehouse_app/backups.py`:

```python
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connections
from django.utils import timezone

from .models import BackupKind, BackupRecord, BackupStatus
from .version import APP_VERSION


class BackupError(Exception):
    """Raised when a local backup or restore operation cannot be completed safely."""


@dataclass(frozen=True)
class BackupPaths:
    database_path: Path
    backup_dir: Path


def configured_backup_paths() -> BackupPaths:
    database_name = settings.DATABASES["default"]["NAME"]
    database_path = Path(database_name).expanduser()
    backup_dir = Path(getattr(settings, "WAREHOUSE_BACKUP_DIR", settings.WAREHOUSE_DATA_DIR / "backups")).expanduser()
    return BackupPaths(database_path=database_path, backup_dir=backup_dir)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_filename(kind: str, now: datetime | None = None) -> str:
    timestamp = (now or timezone.now()).strftime("%Y%m%d-%H%M%S")
    return f"meridian-{timestamp}-{kind}.sqlite3"


def ensure_sqlite_database(path: Path) -> None:
    if not path.exists():
        raise BackupError(f"Database file does not exist: {path}")
    if not path.is_file():
        raise BackupError(f"Database path is not a file: {path}")


def create_local_backup(
    *,
    database_path: Path | None = None,
    backup_dir: Path | None = None,
    kind: str = BackupKind.MANUAL,
    app_version: str = APP_VERSION,
    message: str = "",
    metadata: dict[str, Any] | None = None,
    created_by=None,
) -> BackupRecord:
    paths = configured_backup_paths()
    source_path = Path(database_path or paths.database_path).expanduser()
    target_dir = Path(backup_dir or paths.backup_dir).expanduser()

    ensure_sqlite_database(source_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / backup_filename(kind)

    try:
        with sqlite3.connect(source_path) as source_connection:
            with sqlite3.connect(target_path) as backup_connection:
                source_connection.backup(backup_connection)
    except sqlite3.Error as exc:
        raise BackupError(f"SQLite backup failed: {exc}") from exc

    size_bytes = target_path.stat().st_size
    checksum = sha256_file(target_path)

    return BackupRecord.objects.create(
        kind=kind,
        status=BackupStatus.CREATED,
        backup_path=str(target_path),
        source_database_path=str(source_path),
        size_bytes=size_bytes,
        sha256=checksum,
        app_version=app_version,
        message=message,
        metadata=metadata or {},
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
    )


def create_pre_migration_backup_if_needed() -> BackupRecord | None:
    paths = configured_backup_paths()
    if not paths.database_path.exists():
        return None
    return create_local_backup(
        database_path=paths.database_path,
        backup_dir=paths.backup_dir,
        kind=BackupKind.PRE_MIGRATION,
        message="Automatic backup before migrations.",
        metadata={"reason": "pre_migration"},
    )


def restore_local_backup(*, backup_path: Path, database_path: Path | None = None) -> None:
    paths = configured_backup_paths()
    source_path = Path(backup_path).expanduser()
    target_path = Path(database_path or paths.database_path).expanduser()

    ensure_sqlite_database(source_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    connections.close_all()
    with sqlite3.connect(source_path) as source_connection:
        with sqlite3.connect(target_path) as target_connection:
            source_connection.backup(target_connection)
```

- [ ] **Step 4: Run service tests**

Run:

```bash
python manage.py test warehouse_app.tests.LocalBackupServiceTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add warehouse_app/backups.py warehouse_app/tests.py
git commit -m "feat: add local sqlite backup service"
```

---

### Task 3: Add Backup Management Commands

**Files:**
- Create: `warehouse_app/management/commands/create_local_backup.py`
- Create: `warehouse_app/management/commands/restore_local_backup.py`
- Modify: `warehouse_app/tests.py`

- [ ] **Step 1: Write failing command tests**

Append this test class to `warehouse_app/tests.py`:

```python
class LocalBackupCommandTests(TestCase):
    def test_create_local_backup_command_creates_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "db.sqlite3"

            with sqlite3.connect(db_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
                connection.commit()

            with override_settings(
                DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": db_path}},
                WAREHOUSE_DATA_DIR=temp_path,
            ):
                call_command("create_local_backup", verbosity=0)

            self.assertEqual(BackupRecord.objects.count(), 1)
            self.assertEqual(BackupRecord.objects.get().kind, BackupKind.MANUAL)

    def test_restore_local_backup_requires_confirm(self):
        with self.assertRaises(CommandError):
            call_command("restore_local_backup", "/tmp/example.sqlite3", verbosity=0)
```

Add imports:

```python
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
```

Reuse existing imports when present.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python manage.py test warehouse_app.tests.LocalBackupCommandTests
```

Expected: FAIL because the commands do not exist.

- [ ] **Step 3: Implement create command**

Create `warehouse_app/management/commands/create_local_backup.py`:

```python
from django.core.management.base import BaseCommand, CommandError

from warehouse_app.backups import BackupError, create_local_backup
from warehouse_app.models import BackupKind


class Command(BaseCommand):
    help = "Create a local SQLite backup for the configured database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind",
            choices=[BackupKind.MANUAL, BackupKind.PRE_MIGRATION, BackupKind.PRE_RESTORE],
            default=BackupKind.MANUAL,
            help="Backup kind recorded in metadata.",
        )

    def handle(self, *args, **options):
        try:
            record = create_local_backup(kind=options["kind"], message="Backup created from management command.")
        except BackupError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Backup created: {record.backup_path}"))
```

- [ ] **Step 4: Implement restore command**

Create `warehouse_app/management/commands/restore_local_backup.py`:

```python
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from warehouse_app.backups import BackupError, create_local_backup, restore_local_backup
from warehouse_app.models import BackupKind


class Command(BaseCommand):
    help = "Restore the configured local SQLite database from a backup file."

    def add_arguments(self, parser):
        parser.add_argument("backup_path", help="Path to the SQLite backup file.")
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required confirmation flag. Restore replaces the configured database.",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("Restore requires --confirm because it replaces the configured database.")

        backup_path = Path(options["backup_path"]).expanduser()

        try:
            create_local_backup(kind=BackupKind.PRE_RESTORE, message="Automatic backup before restore.")
            restore_local_backup(backup_path=backup_path)
        except BackupError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Database restored from: {backup_path}"))
```

- [ ] **Step 5: Run command tests**

Run:

```bash
python manage.py test warehouse_app.tests.LocalBackupCommandTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add warehouse_app/management/commands/create_local_backup.py warehouse_app/management/commands/restore_local_backup.py warehouse_app/tests.py
git commit -m "feat: add local backup management commands"
```

---

### Task 4: Add Admin-Only Backup UI

**Files:**
- Modify: `warehouse_app/permissions.py`
- Modify: `warehouse_app/views.py`
- Modify: `warehouse_app/urls.py`
- Create: `templates/warehouse_app/backup_list.html`
- Modify: `templates/base.html`
- Modify: `warehouse_app/tests.py`

- [ ] **Step 1: Write failing permission and UI tests**

Append this test class to `warehouse_app/tests.py`:

```python
class BackupViewTests(TestCase):
    def test_viewer_cannot_open_backup_list(self):
        user = User.objects.create_user(username="viewer", password="pass")
        UserProfile.objects.create(user=user, role=UserRole.VIEWER)
        self.client.force_login(user)

        response = self.client.get(reverse("backup_list"))

        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_backup_from_ui(self):
        user = User.objects.create_user(username="admin", password="pass")
        UserProfile.objects.create(user=user, role=UserRole.ADMIN)
        self.client.force_login(user)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "db.sqlite3"

            with sqlite3.connect(db_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
                connection.commit()

            with override_settings(
                DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": db_path}},
                WAREHOUSE_DATA_DIR=temp_path,
            ):
                response = self.client.post(reverse("backup_create"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BackupRecord.objects.count(), 1)
        self.assertContains(response, "Резервная копия создана")
```

Add imports:

```python
from django.contrib.auth.models import User
from django.urls import reverse
```

Reuse existing imports when present.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python manage.py test warehouse_app.tests.BackupViewTests
```

Expected: FAIL because backup URLs/views do not exist.

- [ ] **Step 3: Add backup permissions**

Add to `warehouse_app/permissions.py`:

```python
def can_manage_backups(user) -> bool:
    return get_user_role(user) == UserRole.ADMIN


def require_backup_manager(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not can_manage_backups(request.user):
            raise PermissionDenied("Недостаточно прав для управления резервными копиями.")
        return view_func(request, *args, **kwargs)

    return wrapper
```

- [ ] **Step 4: Add backup views**

In `warehouse_app/views.py`, add imports:

```python
from pathlib import Path

from django.http import FileResponse, Http404

from .backups import BackupError, configured_backup_paths, create_local_backup
from .models import BackupRecord
from .permissions import require_backup_manager
```

If `Path`, `FileResponse`, `Http404`, or project imports already exist, merge with existing imports.

Add these views:

```python
@require_backup_manager
def backup_list(request):
    paths = configured_backup_paths()
    records = BackupRecord.objects.select_related("created_by")[:50]
    return render(
        request,
        "warehouse_app/backup_list.html",
        {
            "records": records,
            "database_path": paths.database_path,
            "backup_dir": paths.backup_dir,
        },
    )


@require_backup_manager
def backup_create(request):
    if request.method != "POST":
        return redirect("backup_list")

    try:
        create_local_backup(message="Manual backup created from web UI.", created_by=request.user)
    except BackupError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Резервная копия создана.")

    return redirect("backup_list")


@require_backup_manager
def backup_download(request, pk: int):
    record = get_object_or_404(BackupRecord, pk=pk)
    path = Path(record.backup_path)
    if not path.exists() or not path.is_file():
        raise Http404("Backup file not found.")
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)
```

If `get_object_or_404`, `messages`, `redirect`, and `render` are already imported, reuse existing imports.

- [ ] **Step 5: Add URLs**

Add to `warehouse_app/urls.py`:

```python
path("backups/", views.backup_list, name="backup_list"),
path("backups/create/", views.backup_create, name="backup_create"),
path("backups/<int:pk>/download/", views.backup_download, name="backup_download"),
```

Place these near admin/operations routes, before report/export routes.

- [ ] **Step 6: Add template**

Create `templates/warehouse_app/backup_list.html`:

```html
{% extends "base.html" %}

{% block title %}Резервные копии{% endblock %}

{% block content %}
<section class="page-header">
    <div>
        <p class="eyebrow">Local Single User</p>
        <h2>Резервные копии</h2>
        <p>Создание локальных копий SQLite-базы для восстановления после ошибки, обновления или миграции.</p>
    </div>
    <form method="post" action="{% url 'backup_create' %}">
        {% csrf_token %}
        <button type="submit" class="button primary" onclick="return confirm('Создать резервную копию текущей базы?');">Создать копию</button>
    </form>
</section>

<section class="card">
    <h3>Расположение данных</h3>
    <dl class="definition-list">
        <dt>База данных</dt>
        <dd><code>{{ database_path }}</code></dd>
        <dt>Папка копий</dt>
        <dd><code>{{ backup_dir }}</code></dd>
    </dl>
    <p class="muted">Восстановление выполняется через management command, а не из работающего web-интерфейса.</p>
</section>

<section class="card">
    <h3>Последние копии</h3>
    {% if records %}
        <table>
            <thead>
                <tr>
                    <th>Создана</th>
                    <th>Тип</th>
                    <th>Статус</th>
                    <th>Размер</th>
                    <th>Версия</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {% for record in records %}
                    <tr>
                        <td>{{ record.created_at|date:"d.m.Y H:i" }}</td>
                        <td>{{ record.get_kind_display }}</td>
                        <td>{{ record.get_status_display }}</td>
                        <td>{{ record.size_bytes }} байт</td>
                        <td>{{ record.app_version }}</td>
                        <td><a href="{% url 'backup_download' record.pk %}">Скачать</a></td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p class="empty-state">Резервные копии еще не созданы. Создайте первую копию перед реальным вводом данных.</p>
    {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 7: Add navigation link**

In `templates/base.html`, add this inside the `Обзор` group after `Первичная настройка`:

```html
<a href="{% url 'backup_list' %}" class="{% if request.resolver_match.url_name == 'backup_list' %}active{% endif %}">Резервные копии</a>
```

- [ ] **Step 8: Run UI tests**

Run:

```bash
python manage.py test warehouse_app.tests.BackupViewTests
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add warehouse_app/permissions.py warehouse_app/views.py warehouse_app/urls.py templates/base.html templates/warehouse_app/backup_list.html warehouse_app/tests.py
git commit -m "feat: add local backup UI"
```

---

### Task 5: Add Pre-Migration Backup Hook To Sidecar

**Files:**
- Modify: `desktop/python_sidecar/serve.py`
- Modify: `warehouse_app/tests.py`
- Modify: `desktop/python_sidecar/README.md`

- [ ] **Step 1: Write failing test for pre-migration helper**

Append this test to `LocalBackupServiceTests`:

```python
    def test_create_pre_migration_backup_skips_missing_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with override_settings(
                DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": temp_path / "db.sqlite3"}},
                WAREHOUSE_DATA_DIR=temp_path,
            ):
                record = create_pre_migration_backup_if_needed()

        self.assertIsNone(record)
```

Add import:

```python
from warehouse_app.backups import create_pre_migration_backup_if_needed
```

- [ ] **Step 2: Run test**

Run:

```bash
python manage.py test warehouse_app.tests.LocalBackupServiceTests
```

Expected: PASS if Task 2 implemented `create_pre_migration_backup_if_needed`; otherwise FAIL and then add the function exactly as defined in Task 2.

- [ ] **Step 3: Update sidecar startup**

Modify `desktop/python_sidecar/serve.py` inside `build_wsgi_application()` before `call_command("migrate", ...)`:

```python
    if env_flag("WAREHOUSE_AUTO_MIGRATE", default=True):
        from django.core.management import call_command

        from warehouse_app.backups import BackupError, create_pre_migration_backup_if_needed

        try:
            create_pre_migration_backup_if_needed()
        except BackupError as exc:
            print(f"Pre-migration backup failed: {exc}", file=sys.stderr)
            raise

        call_command("migrate", interactive=False, verbosity=0)
```

This intentionally fails startup if an existing database cannot be backed up before migration.

- [ ] **Step 4: Document sidecar behavior**

In `desktop/python_sidecar/README.md`, add under the auto-migrate section:

```markdown
Before automatic migration, the sidecar creates a `pre_migration` SQLite backup when the configured database file already exists. If this backup cannot be created, startup fails instead of migrating an unprotected local database.
```

- [ ] **Step 5: Run tests**

Run:

```bash
python manage.py test warehouse_app.tests.LocalBackupServiceTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add desktop/python_sidecar/serve.py desktop/python_sidecar/README.md warehouse_app/tests.py
git commit -m "feat: backup before sidecar migrations"
```

---

### Task 6: Document Restore Procedure And Local Data Guarantees

**Files:**
- Modify: `docs/TECH_SPEC.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/DESKTOP_APP.md`

- [ ] **Step 1: Update TECH_SPEC**

In `docs/TECH_SPEC.md`, add to confirmed requirements near existing backup/restore bullets:

```markdown
- Local Single User профиль должен поддерживать ручное создание резервной копии локальной SQLite-базы.
- Restore локальной SQLite-базы должен быть описан и доступен через management command с явным подтверждением; web restore не должен появляться без отдельного безопасного design.
- Перед автоматическими desktop migrations должен создаваться `pre_migration` backup, если локальная база уже существует.
```

- [ ] **Step 2: Update ARCHITECTURE**

In `docs/ARCHITECTURE.md`, add under `Deployment Boundaries`:

```markdown
- Backup/restore layer относится к deployment safety, а не к доменной складской логике.
- Web UI может создавать и скачивать backup, но restore выполняется вне активного web request через management command.
- Desktop sidecar обязан создавать pre-migration backup перед автоматическим `migrate` для существующей SQLite-базы.
```

- [ ] **Step 3: Update STATUS**

In `docs/STATUS.md`, move the backup/restore limitation into a more precise state after implementation:

```markdown
- есть ручное создание и скачивание локальных SQLite backup для `Local Single User` профиля;
- есть restore procedure через management command с обязательным `--confirm`;
- есть automatic pre-migration backup в desktop sidecar для существующей SQLite-базы;
- нет web restore UI, scheduled backups, encryption and cloud backup.
```

Keep unknown or future work listed as limitations.

- [ ] **Step 4: Update ROADMAP**

In `docs/ROADMAP.md`, under Stage C `Data safety`, mark the first slice as implemented in prose:

```markdown
First slice target: local manual backup, restore command, and pre-migration backup for SQLite. Scheduled/cloud/encrypted backups remain outside this slice.
```

- [ ] **Step 5: Update DESKTOP_APP docs**

In `docs/DESKTOP_APP.md`, add a short operator note:

```markdown
For Local Single User deployments, the user data directory contains the SQLite database and `backups/`. Before automatic migration, the sidecar creates a pre-migration backup when the database exists.
```

- [ ] **Step 6: Run doc hygiene**

Run:

```bash
python scripts/check_public_readiness.py
git diff --check
```

Expected: both pass.

- [ ] **Step 7: Commit**

```bash
git add docs/TECH_SPEC.md docs/ARCHITECTURE.md docs/STATUS.md docs/ROADMAP.md docs/DESKTOP_APP.md
git commit -m "docs: document local data safety flow"
```

---

### Task 7: Full Verification And PR

**Files:**
- No new files.

- [ ] **Step 1: Run targeted backup tests**

Run:

```bash
python manage.py test \
  warehouse_app.tests.BackupRecordModelTests \
  warehouse_app.tests.LocalBackupServiceTests \
  warehouse_app.tests.LocalBackupCommandTests \
  warehouse_app.tests.BackupViewTests
```

Expected: PASS.

- [ ] **Step 2: Run full Django tests**

Run:

```bash
python manage.py test
```

Expected: PASS.

- [ ] **Step 3: Run Django checks**

Run:

```bash
python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 4: Remove generated cache directories if needed**

If public readiness reports generated Python cache directories, run:

```bash
rm -rf config/__pycache__ warehouse_app/__pycache__ warehouse_app/templatetags/__pycache__
```

- [ ] **Step 5: Run public-readiness and whitespace checks**

Run:

```bash
python scripts/check_public_readiness.py
git diff --check
```

Expected: both pass.

- [ ] **Step 6: Manual browser smoke**

Run local server:

```bash
python manage.py runserver 127.0.0.1:8000
```

Open:

```text
http://127.0.0.1:8000/backups/
```

Verify:

- admin/local mode can open the page;
- viewer receives 403;
- create backup button creates a record;
- download link returns a `.sqlite3` file;
- page shows configured database path and backup directory;
- restore is not offered as a web button.

- [ ] **Step 7: Prepare PR**

Run:

```bash
git status --short
git log --oneline --max-count=8
```

Expected:

- only intended commits are present;
- no generated cache directories are tracked;
- working tree is clean.

Push and open PR:

```bash
git push -u origin stage-c-local-data-safety
gh pr create --title "Add local data safety backups" --body "## Summary
- add local SQLite backup metadata and service
- add admin backup UI and management commands
- create pre-migration backup from the desktop sidecar
- document Local Single User data safety flow

## Verification
- python manage.py test
- python manage.py check
- python scripts/check_public_readiness.py
- git diff --check"
```

- [ ] **Step 8: Handle review comments**

Check PR comments:

```bash
gh pr view --json comments,reviews,reviewDecision
gh api repos/k-kostin/meridian/pulls/<PR_NUMBER>/comments
```

If Gemini or another reviewer raises actionable issues, address them in a follow-up commit on the same branch, rerun the relevant tests, push, and re-check comments.

---

## Self-Review

Spec coverage:

- Backup/restore flow: covered by Tasks 2, 3, 4, and 6.
- SQLite local data-dir safety: covered by Tasks 2, 5, and 6.
- Pre-migration backup: covered by Task 5.
- One core / two profiles: preserved because all changes live in deployment safety and do not fork stock-accounting logic.
- Commercial pilot readiness: this implements the first data-safety slice only; user attribution and audit hardening remain separate slices.

Placeholder scan:

- No open-ended implementation placeholders.
- Every code-changing task contains concrete code blocks and commands.

Type consistency:

- `BackupKind`, `BackupStatus`, `BackupRecord`, `BackupError`, `create_local_backup`, `create_pre_migration_backup_if_needed`, and `restore_local_backup` names are consistent across tasks.
- URL names `backup_list`, `backup_create`, and `backup_download` are consistent across tests, routes, views, and template snippets.
