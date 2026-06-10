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
