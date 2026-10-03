"""
Aether.OS: авторизация для экрана входа (login.js).

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


# =========================================================
# SETTINGS
# =========================================================

NODE_NAME = "NODE-07"

GUEST_LEVEL = 0
DEFAULT_USER_LEVEL = 1

CLEARANCE_LABELS = {
    0: "PUBLIC",
    1: "INTERNAL",
    2: "CONFIDENTIAL",
    3: "RESTRICTED",
    4: "SECRET",
    5: "TOP SECRET",
}

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
    """Формат, который ждёт login.js: {"level": "L3", "label": "RESTRICTED"}"""
    return {
        "level": f"L{level}",
        "label": CLEARANCE_LABELS.get(level, "UNKNOWN"),
    }


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
# BOOT PAGE
# =========================================================

def build_boot_config(request):
    """Данные для boot.js и login.js (читаются из json_script boot-config)"""
    level = current_level(request)
    is_guest = bool(request.session.get("guest")) and not request.user.is_authenticated

    config = {
        "node": NODE_NAME,
        "authenticated": level is not None,
        "guest": is_guest,
    }

    if level is not None:
        config["username"] = "guest" if is_guest else request.user.get_username()
        config["clearance"] = clearance_dict(level)

    return config


@ensure_csrf_cookie  # без этого fetch из login.js не получит csrftoken
def boot_page(request):
    return render(request, "boot.html", {"boot_config": build_boot_config(request)})


# =========================================================
# API
# ========================================================


@require_POST
def guest_api(request):
    logout(request)  # сбрасывает сессию, если кто-то был залогинен
    request.session["guest"] = True

    return JsonResponse({
        "username": "guest",
        "clearance": clearance_dict(GUEST_LEVEL),
    })


@ensure_csrf_cookie  # нужна для POST на guest_api
def lock_page(request):
    return render(request, "boot/lock.html", {"boot_config": build_boot_config(request)})


@require_POST
def logout_api(request):
    logout(request)
    return JsonResponse({"ok": True})