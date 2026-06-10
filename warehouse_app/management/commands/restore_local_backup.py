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
