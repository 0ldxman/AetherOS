from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.urls import Resolver404, resolve

from machines.current import machine_has_app, wiki_allows

SPECIAL_RULES = {
    "wiki": wiki_allows,
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