"""Мост эфира с Discord отдельным процессом (обычно он поднимается сам вместе с сайтом). Нужен DISCORD_BOT_TOKEN."""
from django.core.management.base import BaseCommand, CommandError

from air import bridge, discord_bot


class Command(BaseCommand):
    help = "Run the air bridge with Discord (needs DISCORD_BOT_TOKEN)."

    def handle(self, *args, **options):
        if not bridge.token():
            raise CommandError("DISCORD_BOT_TOKEN is not set")
        self.stdout.write("air bridge: waiting for the lease and connecting to Discord…")
        discord_bot.run()
