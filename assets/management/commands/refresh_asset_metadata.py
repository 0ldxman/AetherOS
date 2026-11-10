from django.core.management.base import BaseCommand

from assets.nextcloud import NextcloudClient
from filesystem.models import Item


class Command(BaseCommand):
    help = "Заполняет имя, тип и размер файла у объектов с файлом в хранилище."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Обновить все объекты с файлом, а не только с пустыми сведениями.")

    def handle(self, *args, **options):
        found = Item.objects.exclude(file_id="")
        if not options["all"]:
            found = found.filter(file_name="")

        client = NextcloudClient.from_settings()
        ok = failed = 0
        for item in found:
            try:
                item.refresh_file(client=client)
            except Exception as exc:
                failed += 1
                self.stderr.write(f"[{item.pk}] {item.name}: {exc}")
                continue
            item.save(update_fields=["file_name", "file_type", "file_size"])
            ok += 1

        self.stdout.write(self.style.SUCCESS(f"Обновлено: {ok}, ошибок: {failed}"))
