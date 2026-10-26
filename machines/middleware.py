from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.urls import Resolver404, resolve

from machines.current import machine_has_app, wiki_allows

def map_allows(request, match):
    """Карта нужна и окну вики: виджет ::map встраивает её (?embed=1) на машинах без иконки карты."""
    # редакторы карты работают внутри админки у персонала, машина в сессии им не нужна
    if getattr(request.user, "is_staff", False):
        return True
    if machine_has_app(request, "map"):
        return True
    if not machine_has_app(request, "wiki"):
        return False
    # данные карты (api, таймлайн) открыты окну вики; саму страницу пускаем только во встроенном виде
    return match.url_name != "index" or request.GET.get("embed") == "1"


SPECIAL_RULES = {
    "wiki": wiki_allows,
    "map": map_allows,
}


class MachineAppMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return self.get_response(request)

        for namespace in match.namespaces:
            if namespace in settings.MACHINE_APP_NAMESPACES:
                rule = SPECIAL_RULES.get(namespace)

                if rule is not None:
                    allowed = rule(request, match)
                else:
                    allowed = machine_has_app(request, namespace)

                if not allowed:
                    raise PermissionDenied
                break

        return self.get_response(request)