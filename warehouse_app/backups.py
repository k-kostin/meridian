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


def _next_backup_path(backup_dir: Path, kind: str) -> Path:
    candidate = backup_dir / backup_filename(kind)
    if not candidate.exists():
        return candidate

    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S-%f")
    return backup_dir / f"meridian-{timestamp}-{kind}.sqlite3"


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
    target_path = _next_backup_path(target_dir, kind)

    try:
        with sqlite3.connect(source_path) as source_connection:
            with sqlite3.connect(target_path) as backup_connection:
                source_connection.backup(backup_connection)
    except sqlite3.Error as exc:
        raise BackupError(f"SQLite backup failed: {exc}") from exc

    return BackupRecord.objects.create(
        kind=kind,
        status=BackupStatus.CREATED,
        backup_path=str(target_path),
        source_database_path=str(source_path),
        size_bytes=target_path.stat().st_size,
        sha256=sha256_file(target_path),
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
