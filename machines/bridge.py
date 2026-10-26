"""Мост: игрок входит с одной машины на другую из терминала (команда bridge).

Состояние живёт в Django-сессии, на сервере, браузер его подменить не может:

    machine_session_id   сессия машины, на которой игрок сейчас (её читают все приложения);
    bridge_stack         сессии, из которых игрок пришёл, путь назад: [A, B] при цепочке A -> B -> C.

Вход кладёт текущую сессию в стек и делает активной сессию целевой записи, выход достаёт из стека.
Сессия для пары (игрок, запись) переиспользуется: прогресс по файлам и счётчики попыток остаются между визитами.

Условия входа, их проверяет verdict():
    пароль    нужен, если у записи он задан (хеш);
    ключ      нужен, если у записи есть условие по ключам: игрок предъявляет файл-ключ (-i), в нём
              должны быть ключи, удовлетворяющие условию;
    токен     заменяет и пароль, и ключ; у него свои срок и число использований.
Записи с паролем и ключом требуют и то и другое. Если задан список hid, входить можно только с машин из него.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.contrib.auth.hashers import check_password
from django.db.models import F
from django.utils import timezone

from secure.access import satisfied

from .current import SESSION_KEY, active_session
from .models import Machine, MachineProfile, MachineProfileToken, Session

STACK_KEY = "bridge_stack"
SHELL_KEY = "rshell_stack"
MAX_DEPTH = 4


# ---------- стек ----------

def depth(request):
    return len(request.session.get(STACK_KEY, []))


def session_for(user, profile):
    """Сессия пары (игрок, запись): переиспользуется между визитами, прогресс по файлам остаётся."""
    session = Session.objects.filter(user=user, profile=profile).select_related("profile__machine").order_by("-pk").first()
    if session is None:
        session = Session.objects.create(user=user, profile=profile)
    return session


def enter(request, profile):
    """Игрок вошёл на запись profile: текущая сессия уходит в стек, активной становится сессия записи."""
    source = active_session(request)
    session = session_for(request.user, profile)

    request.session[STACK_KEY] = [*request.session.get(STACK_KEY, []), source.pk]
    request.session[SESSION_KEY] = session.pk
    return session


def leave(request, all_levels=False):
    """Вернуться на уровень выше (или на исходную машину). Возвращает покинутую сессию или None, если выходить некуда."""
    stack = list(request.session.get(STACK_KEY, []))
    if not stack:
        return None

    left = active_session(request)
    request.session[SESSION_KEY] = stack[0] if all_levels else stack[-1]
    request.session[STACK_KEY] = [] if all_levels else stack[:-1]
    return left


# ---------- оболочка на другой машине (rshell) ----------
#
# Рабочий стол остаётся на своей машине, меняется только оболочка терминала. Стек оболочек лежит в той же сессии Django:
# [{"session": pk, "back_cwd": папка}, ...], у верхней записи сессия, на которой сейчас терминал, а back_cwd это папка
# уровнем ниже (туда вернёт exit и от неё считаются локальные пути xfer).

def shell_depth(request):
    return len(request.session.get(SHELL_KEY, []))


def total_depth(request):
    """Все открытые уровни: мосты рабочего стола и оболочки терминала (общий предел вложенности)."""
    return depth(request) + shell_depth(request)


def terminal_session(request):
    """Сессия, на которой сейчас терминал: верхняя оболочка, а без неё сессия рабочего стола."""
    stack = request.session.get(SHELL_KEY, [])
    if stack:
        session = (
            Session.objects.select_related("profile__machine").filter(pk=stack[-1]["session"], user=request.user).first()
        )
        if session is not None:
            return session
    return active_session(request)


def shell_enter(request, profile, back_cwd):
    session = session_for(request.user, profile)
    request.session[SHELL_KEY] = [*request.session.get(SHELL_KEY, []), {"session": session.pk, "back_cwd": back_cwd}]
    return session


def shell_leave(request, all_levels=False):
    """Выйти из оболочки на уровень выше (или из всех). Возвращает (покинутая сессия, папка, в которую вернуться) или None."""
    stack = list(request.session.get(SHELL_KEY, []))
    if not stack:
        return None

    left = terminal_session(request)
    back = stack[0]["back_cwd"] if all_levels else stack[-1]["back_cwd"]
    request.session[SHELL_KEY] = [] if all_levels else stack[:-1]
    return left, back


def shell_clear(request):
    request.session.pop(SHELL_KEY, None)


def shell_parent(request):
    """Уровень ниже верхней оболочки: (сессия, папка). Это «своя» сторона для xfer; None, если оболочки нет."""
    stack = request.session.get(SHELL_KEY, [])
    if not stack:
        return None

    parent = (
        Session.objects.select_related("profile__machine").filter(pk=stack[-2]["session"], user=request.user).first()
        if len(stack) > 1 else active_session(request)
    )
    return parent, stack[-1]["back_cwd"]


# ---------- поиск записи ----------

@dataclass
class Resolution:
    profile: MachineProfile | None = None
    error: str = ""          # no_host | no_account | ambiguous | bad_endpoint


def parse_endpoint(raw):
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def resolve(host, login, endpoint=None):
    """Запись login на машине host. endpoint (частота или порт) нужен, если у логина несколько записей."""
    machine = Machine.objects.filter(hostname=host).first()
    if machine is None:
        return Resolution(error="no_host")

    profiles = list(MachineProfile.objects.filter(machine=machine, login=login))
    if endpoint is not None:
        profiles = [p for p in profiles if p.freq == endpoint]
    if not profiles:
        return Resolution(error="no_account")
    if len(profiles) > 1:
        return Resolution(error="ambiguous")
    return Resolution(profiles[0])


# ---------- условия входа ----------

def password_required(profile):
    return bool(profile.password_hash)


def key_required(profile):
    return bool(profile.key_condition)


def methods(profile):
    """Какие способы входа у записи (для отказа в духе ssh: Permission denied (publickey,password))."""
    return [name for name, needed in (("publickey", key_required(profile)), ("password", password_required(profile))) if needed]


def source_allowed(profile, source_machine):
    """Со списком hid входить можно только с машин из него; пустой список пускает откуда угодно."""
    hids = set(profile.allowed_hids.values_list("hid", flat=True))
    return not hids or source_machine.hid in hids


def valid_token(profile, value):
    """Токен записи, если он существует, не просрочен и не исчерпан; иначе None."""
    token = MachineProfileToken.objects.filter(profile=profile, token=value).first()
    if token is None:
        return None
    if token.expires_at and token.expires_at <= timezone.now():
        return None
    if token.max_usage is not None and token.usage >= token.max_usage:
        return None
    return token


def spend_token(token):
    MachineProfileToken.objects.filter(pk=token.pk).update(usage=F("usage") + 1)


def keys_ok(profile, key_slugs):
    return not key_required(profile) or satisfied(profile.key_condition, frozenset(key_slugs))


def password_ok(profile, password):
    return not password_required(profile) or check_password(password or "", profile.password_hash)
