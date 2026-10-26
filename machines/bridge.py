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
MAX_DEPTH = 4


# ---------- стек ----------

def depth(request):
    return len(request.session.get(STACK_KEY, []))


def enter(request, profile):
    """Игрок вошёл на запись profile: текущая сессия уходит в стек, активной становится сессия записи."""
    source = active_session(request)
    session = Session.objects.filter(user=request.user, profile=profile).order_by("-pk").first()
    if session is None:
        session = Session.objects.create(user=request.user, profile=profile)

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
