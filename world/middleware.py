"""Моменты мира наступают сами: при запросах сайта, не чаще раза в moments.TICK секунд на процесс."""
import logging

log = logging.getLogger("world")


class WorldTickMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(("/static/", "/media/")):
            try:
                from world import moments

                moments.tick()
                from characters import outbox

                outbox.tick()
            except Exception:                               # noqa: BLE001 — мир не должен ронять страницу
                log.exception("world tick failed")
        return self.get_response(request)
