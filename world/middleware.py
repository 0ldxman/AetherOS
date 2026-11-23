"""Моменты мира наступают сами: при запросах сайта, не чаще раза в moments.TICK секунд на процесс."""
import logging
from importlib import import_module

log = logging.getLogger("world")

TICKS = (("moments", "world.moments"), ("outbox", "characters.outbox"), ("rotation", "forum.rotation"), ("graph", "graph.runtime"),
         ("power", "machines.world.power"))


class WorldTickMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(("/static/", "/media/")):
            for name, module in TICKS:                      # каждый тик сам по себе: упавший не останавливает остальные
                try:
                    import_module(module).tick()
                except Exception:                           # noqa: BLE001 — мир не должен ронять страницу
                    log.exception("world tick %s failed", name)
        return self.get_response(request)
