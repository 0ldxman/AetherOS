"""ASGI: обычные запросы Django и WebSocket совместной правки Студии (team.routing), с сессией и пользователем Django."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_application = get_asgi_application()          # до импорта потребителей: приложения Django должны быть готовы

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from team.routing import websocket_urlpatterns  # noqa: E402


class ProxyRootPath:
    """Префикс сайта (FORCE_SCRIPT_NAME, например /proxy/8000 за code-server) прокси срезает из адреса WebSocket, а daphne
    всё равно передаёт его в root_path. Channels тогда требует, чтобы адрес начинался с префикса, и отказывает: такой
    root_path не нужен."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        root = scope.get("root_path", "")
        if root and not scope.get("path", "").startswith(root):
            scope = dict(scope, root_path="")
        return await self.app(scope, receive, send)


websocket_application = ProxyRootPath(AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))))

application = ProtocolTypeRouter({
    "http": django_application,
    "websocket": websocket_application,
})
