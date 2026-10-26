from django.core.management.base import BaseCommand

from filesystem.trash import purge_expired


class Command(BaseCommand):
    help = "Удалить насовсем файлы из корзин игроков, у которых вышел срок (терминал делает это и сам при каждой команде)."

    def handle(self, *args, **options):
        self.stdout.write(f"purged: {purge_expired()}")
