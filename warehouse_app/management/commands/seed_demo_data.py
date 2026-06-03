from django.core.management.base import BaseCommand, CommandError

from warehouse_app.demo import seed_demo_data


class Command(BaseCommand):
    help = "Load demo data into the database. Use --reset to replace existing data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete current business data and reload the demo dataset.",
        )

    def handle(self, *args, **options):
        try:
            summary = seed_demo_data(force_reset=options["reset"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data loaded: "
                f"{summary['warehouses']} warehouses, "
                f"{summary['items']} items, "
                f"{summary['documents']} stock documents, "
                f"{summary['inventories']} inventories."
            )
        )
