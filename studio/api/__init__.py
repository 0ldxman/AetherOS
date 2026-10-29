"""API студии: то, чем пользуется админка автора на Svelte (studio/frontend).

Только для сотрудников, по сессии Django и CSRF (как старая админка). Логика живёт в приложениях (filesystem.manager,
filesystem.history, documents.editor): здесь только проверка входа, схемы и коды ответов. Схема: /studio/api/openapi.json,
из неё фронт строит типы (npm run api).
"""
from django.core.exceptions import ValidationError
from ninja import NinjaAPI
from ninja.security import SessionAuthIsStaff

from filesystem.manager.filemanager import FileManagerError

api = NinjaAPI(title="Aether Studio", version="1", auth=SessionAuthIsStaff(), urls_namespace="studio_api", docs_url="/docs")


@api.exception_handler(FileManagerError)
def _refused(request, exc):
    return api.create_response(request, {"detail": str(exc)}, status=400)


@api.exception_handler(ValidationError)
def _invalid(request, exc):
    fields = exc.message_dict if hasattr(exc, "error_dict") else {"__all__": exc.messages}
    return api.create_response(request, {"detail": "Проверьте поля.", "fields": fields}, status=400)


from studio.api import accounts, catalog, disks, groups, items, machines, policies, systems, volumes  # noqa: E402  (роутеры на api)

api.add_router("/", catalog.router)
api.add_router("/volumes", volumes.router)
api.add_router("/items", items.router)
api.add_router("/machines", machines.router)
api.add_router("/machines", accounts.router)
api.add_router("/machines", groups.router)
api.add_router("/machines", disks.router)
api.add_router("/policies", policies.router)
api.add_router("/systems", systems.router)
