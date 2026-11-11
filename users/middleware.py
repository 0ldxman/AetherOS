"""Песочница автора в браузере: игровые страницы идут от имени его песочного игрока (users/sandbox.py).

Стоит после AuthenticationMiddleware. Если у сотрудника есть подписанная кука песочницы с его id, на запрос к игре (не Студия,
не админка) пользователь подменяется песочным, а сессия Django берётся своя, из отдельной куки: состояние игрока в сессии
(выбранная машина, мост, выбросы) не смешивается с сессией автора. На выходе всё возвращается, чтобы SessionMiddleware сохранил
сессию автора, а не песочницы.
"""
from importlib import import_module

from django.conf import settings

from users import sandbox


class SandboxMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.store = import_module(settings.SESSION_ENGINE).SessionStore

    def __call__(self, request):
        player = self._player(request)
        if player is None:
            return self.get_response(request)
        own_session, own_user = request.session, request.user
        session = self.store(request.COOKIES.get(sandbox.SESSION_COOKIE))
        request.session, request.user = session, player
        request.sandbox_author = own_user
        try:
            response = self.get_response(request)
        finally:
            request.session, request.user = own_session, own_user
        self._keep(session, response)
        return response

    def _player(self, request):
        if request.path_info.startswith(sandbox.OWN_PATHS):
            return None
        author_id = sandbox.author_of(request.COOKIES.get(sandbox.COOKIE))
        user = getattr(request, "user", None)
        if author_id is None or user is None or not user.is_authenticated or not user.is_staff or user.pk != author_id:
            return None
        return sandbox.sandbox_of(user)

    def _keep(self, session, response):
        if not session.modified:
            return
        if session.is_empty():
            response.delete_cookie(sandbox.SESSION_COOKIE, path=settings.SESSION_COOKIE_PATH)
            return
        session.save()
        response.set_cookie(sandbox.SESSION_COOKIE, session.session_key, max_age=sandbox.MAX_AGE, path=settings.SESSION_COOKIE_PATH,
                            secure=settings.SESSION_COOKIE_SECURE, httponly=True, samesite="Lax")
