import os
import sys

from django.apps import AppConfig


def _serving():
    """Процесс сайта (runserver, daphne, gunicorn, uvicorn), а не тесты и не другие команды manage.py."""
    if "runserver" in sys.argv:
        return os.environ.get("RUN_MAIN") == "true" or "--noreload" in sys.argv
    return os.path.basename(sys.argv[0] if sys.argv else "") in ("daphne", "gunicorn", "uvicorn")


class AirConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "air"
    verbose_name = "Эфир"

    def ready(self):
        from air import bridge  # noqa: F401 — очередь моста на сохранение передачи

        # мост с Discord поднимается вместе с сайтом, если задан токен; AIR_BRIDGE_AUTOSTART=0 отключает
        if os.environ.get("AIR_BRIDGE_AUTOSTART", "1") != "0" and bridge.token() and _serving():
            from air import discord_bot

            discord_bot.start_in_background()
