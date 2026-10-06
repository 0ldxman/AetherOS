import json
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from ...models import Province


class Command(BaseCommand):
    help = "Импорт провинций из GeoJSON"

    def add_arguments(self, parser):
        parser.add_argument("path", help="Путь к GeoJSON-файлу")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Удалить все существующие провинции и создать заново",
        )

    def handle(self, *args, **options):
        with open(options["path"], encoding="utf-8") as f:
            data = json.load(f)

        counters = defaultdict(int)
        unknown_sources = 0
        created = updated = 0

        with transaction.atomic():
            if options["force"]:
                deleted, _ = Province.objects.all().delete()
                self.stdout.write(self.style.WARNING(f"Удалено записей: {deleted}"))

            for feature in data["features"]:
                props = feature.get("properties") or {}

                country = props.get("adm0_a3") or "UNKNOWN"
                counters[country] += 1
                code = f"{country}-{counters[country]}"

                source_code = props.get("adm1_code")
                if not source_code:
                    unknown_sources += 1
                    source_code = f"UNKNOWN-{unknown_sources}"

                _, is_new = Province.objects.update_or_create(
                    source_code=source_code,
                    defaults={
                        "code": code,
                        "name": props.get("name") or source_code,
                    },
                )
                if is_new:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(f"Создано: {created}, обновлено: {updated}"))
        if unknown_sources:
            self.stdout.write(self.style.WARNING(f"Без adm1_code: {unknown_sources}"))