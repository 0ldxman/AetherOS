"""Лента и версия для API Студии (team.changes): проверка перед сохранением, запись после успеха, номер в ответе на чтение."""
import json

from django.http import JsonResponse

from team import changes

API_MARK = "/studio/api/"
SAFE = ("GET", "HEAD", "OPTIONS")


class ChangesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if API_MARK not in request.path_info:
            return self.get_response(request)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.is_staff:
            return self.get_response(request)

        path = request.path_info.split(API_MARK, 1)[1].strip("/")
        method = request.method.upper()
        if method in SAFE:
            response = self.get_response(request)
            if response.status_code < 300:
                response["X-Version"] = str(changes.current())
            return response

        if not changes.records(path, method):
            return self.get_response(request)

        if changes.checks(path, method) and not request.headers.get("X-Force"):
            base = request.headers.get("X-Base-Version", "")
            if base.isdigit():
                found = changes.newer(path, int(base))
                if found is not None:
                    return JsonResponse({
                        "detail": changes.conflict_text(found), "stale": True,
                        "by": found.username, "at": found.at.isoformat(), "summary": found.summary,
                    }, status=409)

        described = changes.describe(path) if method == "DELETE" else None
        snap = changes.snapshot(path) if method == "DELETE" else None
        response = self.get_response(request)
        if response.status_code >= 300:
            return response
        created = None
        if method == "POST" and path in changes.COLLECTIONS:
            try:
                created = json.loads(response.content or b"{}")
            except ValueError:
                created = None
            if not isinstance(created, dict):
                created = None
        change = changes.record(user, method, path, created, snap, described)
        response["X-Version"] = str(change.pk)
        return response
