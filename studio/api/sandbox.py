"""Песочница автора: включить, выключить, начать заново. Логика в users/sandbox.py."""
from django.conf import settings
from django.http import HttpResponse
from ninja import Router, Schema

from users import sandbox

router = Router(tags=["sandbox"])


class SbState(Schema):
    open: bool
    player: str            # имя песочного игрока ("" пока его нет)


def _state(request, open_):
    found = sandbox.get_user_model().objects.filter(sandbox_of=request.user).values_list("username", flat=True).first()
    return SbState(open=open_, player=found or "")


@router.get("", response=SbState)
def state(request):
    return _state(request, sandbox.author_of(request.COOKIES.get(sandbox.COOKIE)) == request.user.pk)


@router.post("/open", response=SbState)
def open_(request, response: HttpResponse):
    """Включить песочницу: игровые страницы в этом браузере пойдут от песочного игрока автора."""
    sandbox.sandbox_of(request.user)
    response.set_cookie(sandbox.COOKIE, sandbox.token(request.user), max_age=sandbox.MAX_AGE, path=settings.SESSION_COOKIE_PATH,
                        secure=settings.SESSION_COOKIE_SECURE, httponly=True, samesite="Lax")
    return _state(request, True)


@router.post("/close", response=SbState)
def close(request, response: HttpResponse):
    """Выключить песочницу. Состояние песочного игрока остаётся до «Начать заново»."""
    response.delete_cookie(sandbox.COOKIE, path=settings.SESSION_COOKIE_PATH)
    return _state(request, False)


@router.post("/reset", response=SbState)
def reset(request, response: HttpResponse):
    """Начать заново: песочный игрок со всем состоянием стирается, его сессия тоже."""
    sandbox.reset(request.user)
    response.delete_cookie(sandbox.SESSION_COOKIE, path=settings.SESSION_COOKIE_PATH)
    sandbox.sandbox_of(request.user)
    return _state(request, sandbox.author_of(request.COOKIES.get(sandbox.COOKIE)) == request.user.pk)
