from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from ...models import Country, Province


class Command(BaseCommand):
    help = "Создаёт страны по уникальным префиксам кодов провинций"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=2013,
            help="Год начала существования стран (по умолчанию 2013)",
        )

    def handle(self, *args, **options):
        year = options["year"]

        prefixes = sorted(
            {code.split("-")[0] for code in Province.objects.values_list("code", flat=True)}
        )

        created = 0
        with transaction.atomic():
            for prefix in prefixes:
                _, is_new = Country.objects.get_or_create(
                    code=f"{prefix}-{year}",
                    defaults={
                        "name": prefix,
                        "valid_from": date(year, 1, 1),
                    },
                )
                if is_new:
                    created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Стран в провинциях: {len(prefixes)}, создано новых: {created}")
        )