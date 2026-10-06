from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...models import Country, Ownership, Province


class Command(BaseCommand):
    help = "Создаёт Ownership: каждая провинция принадлежит стране по префиксу её кода"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=2013,
            help="Год страны и начала владения (по умолчанию 2013)",
        )

    def handle(self, *args, **options):
        year = options["year"]
        date_from = date(year, 1, 1)

        countries = {c.code: c for c in Country.objects.filter(code__endswith=f"-{year}")}
        existing = set(
            Ownership.objects.filter(date_from=date_from).values_list("province_id", "country_id")
        )

        to_create = []
        missing = set()

        for province in Province.objects.all():
            prefix = province.code.split("-")[0]
            country = countries.get(f"{prefix}-{year}")
            if country is None:
                missing.add(prefix)
                continue
            if (province.id, country.id) in existing:
                continue
            to_create.append(
                Ownership(
                    province=province,
                    country=country,
                    date_from=date_from,
                    de_jure=True,
                    de_facto=True,
                )
            )

        if missing:
            raise CommandError(
                f"Нет стран для префиксов: {', '.join(sorted(missing))}. "
                f"Сначала запусти import_countries --year {year}"
            )

        with transaction.atomic():
            Ownership.objects.bulk_create(to_create)

        self.stdout.write(self.style.SUCCESS(f"Создано владений: {len(to_create)}"))