"""
Aether.OS: авторизация для экрана входа (сцены в gateway.py, страница в boot/lock.js).

Положите файл в любое приложение проекта (например, core/auth_views.py)
и подключите urls по инструкции из django_setup.md.

Вход через Discord обрабатывает django-allauth, здесь его нет.
"""

import json
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from machines.world import CLEARANCE


# =========================================================
# SETTINGS
# =========================================================

GUEST_LEVEL = 0
GUEST_LOGIN = "witness"   # под этим именем входит игрок без регистрации
DEFAULT_USER_LEVEL = 1


# =========================================================
# GATEWAY (экран входа)
# ---------------------------------------------------------
# Сцены экрана входа собирает users/gateway.py; здесь только данные,
# которых нет в самих сценах: hid машины из базы и допуск гостя.
# =========================================================

def _visitor(request):
    """Кто пришёл: пользователь или (для безымянного) его сессия; от этого зависит ключ клиента."""
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    session = getattr(request, "session", None)
    key = getattr(session, "session_key", None)
    if session is not None and key is None and hasattr(session, "create"):
        session.create()
        key = session.session_key
    return f"session:{key or 'anonymous'}"


def gateway_scenes(request):
    """Сцены экрана входа для этого посетителя (словарь имя -> список шагов)."""
    from machines.identity import client_fingerprint, identity_of

    from . import gateway

    ident = identity_of()
    client_key = client_fingerprint(_visitor(request))

    scenes = {
        "intro": gateway.intro_scene(ident, client_key=client_key),
        "intro_known": gateway.intro_scene(ident, known=True, client_key=client_key),
        "menu": gateway.menu_scene(),
        "discord": gateway.discord_scene(),
        "bypass": gateway.bypass_scene(ident, GUEST_LOGIN),
        "established": gateway.established_scene(clearance_dict(GUEST_LEVEL), GUEST_LOGIN, ident),
        "error": gateway.error_scene(ident),
    }

    level = current_level(request)
    if level is not None:
        is_guest = bool(request.session.get("guest")) and not request.user.is_authenticated
        scenes["restored"] = gateway.restored_scene(
            ident,
            username=GUEST_LOGIN if is_guest else request.user.get_username(),
            clearance=clearance_dict(level),
            guest=is_guest,
        )

    return {name: scene.to_dict() for name, scene in scenes.items()}


# Ограничение перебора пароля: 5 неудач на связку IP + логин, блок на 5 минут


# =========================================================
# CLEARANCE
# =========================================================

def current_level(request):
    """
    Уровень допуска текущего посетителя:
    None  - не авторизован
    0     - гость
    1..N  - пользователь
    """
    if request.user.is_authenticated:
        # TODO: подставьте вашу модель допусков, например
        # return request.user.profile.clearance
        profile = getattr(request.user, "profile", None)
        return getattr(profile, "clearance", DEFAULT_USER_LEVEL)

    if request.session.get("guest"):
        return GUEST_LEVEL

    return None


def clearance_dict(level):
    """Формат для сцен: {"level": "MYS", "label": "mystes"} (код из трёх букв и греческое имя)."""
    code, label = CLEARANCE.get(level, ("???", "unknown"))
    return {"level": code, "label": label}


def clearance_required(min_level):
    """
    Защита представлений на сервере:

        @clearance_required(3)
        def secret_article(request, slug): ...
    """
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            level = current_level(request)

            if level is None or level < min_level:
                raise PermissionDenied

            return view(request, *args, **kwargs)
        return wrapper
    return decorator


# =========================================================
# API
# ========================================================


@require_POST
def guest_api(request):
    logout(request)  # сбрасывает сессию, если кто-то был залогинен
    request.session["guest"] = True

    return JsonResponse({
        "username": GUEST_LOGIN,
        "clearance": clearance_dict(GUEST_LEVEL),
    })


@ensure_csrf_cookie  # нужна для POST на guest_api
def lock_page(request):
    return render(request, "boot/lock.html", {"boot_config": {"scenes": gateway_scenes(request)}})


@require_POST
def logout_api(request):
    logout(request)
    return JsonResponse({"ok": True})