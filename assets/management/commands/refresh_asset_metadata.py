from django.core.management.base import BaseCommand

from assets.models import Asset
from assets.nextcloud import NextcloudClient


class Command(BaseCommand):
    help = "Заполняет filename / content_type / size у существующих ассетов."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Обновить все ассеты, а не только с пустыми метаданными.",
        )

    def handle(self, *args, **options):
        qs = Asset.objects.all()
        if not options["all"]:
            qs = qs.filter(filename="")

        client = NextcloudClient.from_settings()
        ok = failed = 0

        for asset in qs:
            try:
                asset.refresh_metadata(client=client)
            except Exception as exc:
                failed += 1
                self.stderr.write(f"[{asset.pk}] {asset.name}: {exc}")
                continue

            asset.save(
                update_fields=["filename", "content_type", "size", "updated_at"]
            )
            ok += 1

        self.stdout.write(self.style.SUCCESS(f"Обновлено: {ok}, ошибок: {failed}"))