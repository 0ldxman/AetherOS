"""Вход в API Студии: сотрудник по сессии плюс права его роли на раздел запроса (team.rights)."""
from ninja.errors import HttpError
from ninja.security import SessionAuthIsStaff

from team import rights

API_MARK = "/studio/api/"


class StudioAuth(SessionAuthIsStaff):
    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None:
            return None
        path = request.path_info.split(API_MARK, 1)[-1]
        rule = rights.rule_for(path, request.method)
        if rule is None:
            raise HttpError(403, "Путь API не отнесён ни к одному разделу.")
        reason = rights.refusal(user, rule)
        if reason:
            raise HttpError(403, reason)
        return user
