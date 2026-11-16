"""Что сценарий меняет у машины и её учёток: свойства машины, почта, пароль, доступ по ключам, точки входа, группы, токены,
блокировки, создание и удаление учёток. Ошибка — EditError с текстом для журнала сценария.

Учётка по проводу — «логин@хост» (account_key / account).
"""
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth.hashers import make_password
from django.utils import timezone


class EditError(Exception):
    pass


# ---------- машина ----------

def booted_at(text):
    """«Включена с»: «ГГГГ-ММ-ДД ЧЧ:ММ» (игровое время, UTC) или «сейчас»."""
    from machines.world import chrono

    text = str(text or "").strip()
    if text.lower() in ("сейчас", "now"):
        return chrono.game_now()
    for form in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, form).replace(tzinfo=dt_timezone.utc)
        except ValueError:
            continue
    raise EditError(f"«Включена с»: не дата «{text}» (пишите 2031-03-02 14:05 или «сейчас»)")


UNSET = object()


def change_machine(machine, *, name="", address="", system="", time_zone="", host_key="", note=None, booted="", display=None, seats=UNSET,
                   lag="", noise=""):
    """Свойства машины для всех; пустое — не трогать. host_key «*» — новый случайный отпечаток. display — есть ли графическая оболочка,
    seats — сколько игроков одновременно (None — без ограничения)."""
    from machines.models import SystemType
    from machines.world import chrono, identity

    if name:
        machine.name = name[:255]
    if address:
        machine.address = address[:64]
    if system:
        if not SystemType.objects.filter(code=system).exists():
            raise EditError(f"нет ОС «{system}»")
        machine.system = system
    if time_zone:
        if not chrono.valid_zone(time_zone):
            raise EditError(f"нет часового пояса «{time_zone}»")
        machine.time_zone = time_zone
    if host_key:
        machine.host_key = identity.generate_host_key() if host_key.strip() == "*" else host_key.strip()[:64]
    if note is not None:
        machine.note = note
    if booted:
        machine.booted_at = booted_at(booted)
    if display is not None:
        machine.display = bool(display)
    if seats is not UNSET:
        machine.seats = None if seats in (None, "") else max(0, int(seats))
    if lag:
        if lag not in type(machine).Lag.values:
            raise EditError(f"задержка: {lag}?")
        machine.lag = lag
    if noise:
        if noise not in type(machine).Noise.values:
            raise EditError(f"помехи: {noise}?")
        machine.noise = noise
    machine.save()
    return machine


# ---------- учётки ----------

def account_key(profile):
    return f"{profile.login}@{profile.machine.hostname}" if profile is not None and profile.machine.hostname else ""


def account(key):
    """Учётка по «логин@хост» или None."""
    from machines.models import MachineProfile

    login, _, host = str(key or "").strip().rpartition("@")
    if not login or not host:
        return None
    return MachineProfile.objects.select_related("machine").filter(machine__hostname__iexact=host, login=login).first()


def set_mail(profile, mail):
    from mail.addresses import validate_address

    mail = str(mail or "").strip() or f"{profile.login}@{profile.machine.label}"
    try:
        validate_address(mail)
    except Exception as error:                     # noqa: BLE001 — текст ошибки адреса
        raise EditError(f"почта «{mail}»: {error}") from error
    profile.mail = mail
    profile.save(update_fields=["mail"])


def set_password(profile, password):
    """Пароль для всех; пусто — без пароля."""
    profile.password_hash = make_password(str(password)) if str(password or "") else ""
    profile.save(update_fields=["password_hash"])


def set_keys(profile, expression):
    """Выражение ключей (как в учётке: cardkey and badge); пусто — без ключей."""
    from documents.markup.expr import SpoilerSyntaxError, parse_expr

    try:
        profile.key_condition = parse_expr(expression) if str(expression or "").strip() else None
    except SpoilerSyntaxError as error:
        raise EditError(f"выражение ключей: {error}") from error
    profile.save(update_fields=["key_condition"])


def _points(values):
    from machines.models.account import endpoint

    found = [endpoint(value) for value in values if str(value).strip()]
    if None in found:
        raise EditError("точка входа — число: частота (14.230) или порт (22)")
    return [point for point in found if float(point) != 0]


def add_endpoints(profile, values):
    profile.endpoints = sorted(set(profile.endpoints or []) | set(_points(values)), key=float)
    profile.save(update_fields=["endpoints"])


def remove_endpoints(profile, values):
    gone = set(_points(values))
    profile.endpoints = [point for point in profile.endpoints or [] if point not in gone]
    profile.save(update_fields=["endpoints"])


def add_groups(profile, names):
    profile.groups = sorted(set(profile.groups or []) | {str(name).strip() for name in names if str(name).strip()})
    profile.save(update_fields=["groups"])


def remove_groups(profile, names):
    gone = {str(name).strip() for name in names}
    profile.groups = [name for name in profile.groups or [] if name not in gone]
    profile.save(update_fields=["groups"])


def create_token(profile, uses=None, minutes=None):
    """Новый токен входа: строкой (её можно вписать в письмо). uses — сколько раз, minutes — сколько минут живёт; пусто — без предела."""
    from machines.models import MachineProfileToken

    token = f"tk-{secrets.token_urlsafe(9)}"
    MachineProfileToken.objects.create(profile=profile, token=token, max_usage=uses or None,
                                       expires_at=timezone.now() + timedelta(minutes=minutes) if minutes else None)
    return token


def delete_tokens(profile, tokens=()):
    """Удалить токены по строкам; пустой список — все токены учётки. Возвращает сколько."""
    found = profile.tokens.all()
    names = [str(token).strip() for token in tokens if str(token).strip()]
    if names:
        found = found.filter(token__in=names)
    count = found.count()
    found.delete()
    return count


def block(profile, user, minutes, text=""):
    """Заблокировать вход: игроку user или всем (user None) на minutes минут."""
    from machines.models import AccountBlock

    AccountBlock.objects.create(profile=profile, user=user, until=timezone.now() + timedelta(minutes=max(1, int(minutes or 1))), text=str(text or "")[:255])


def unblock(profile, user=None, everyone=False):
    """Снять блокировки: игрока user или все (everyone)."""
    from machines.models import AccountBlock

    found = AccountBlock.objects.filter(profile=profile)
    if not everyone:
        found = found.filter(user=user)
    found.delete()


def create(machine, login, *, name="", endpoints=(), password="", mail="", groups=(), user=None):
    """Новая учётка на машине; user — учётка этого игрока (его место на машине, одна на машину). Логин занят — EditError."""
    from machines.models import MachineProfile

    login = str(login or "").strip()
    if not login or "@" in login or " " in login:
        raise EditError(f"логин «{login}» не подходит")
    if MachineProfile.objects.filter(machine=machine, login=login).exists():
        raise EditError(f"учётка {login}@{machine.hostname} уже есть")
    if user is not None and MachineProfile.objects.filter(machine=machine, user=user).exists():
        raise EditError(f"у игрока {user.get_username()} уже есть учётка на {machine.hostname}")
    profile = MachineProfile(machine=machine, user=user, login=login, name=str(name or "").strip() or login, endpoints=_points(endpoints),
                             groups=sorted({str(g).strip() for g in groups if str(g).strip()}),
                             password_hash=make_password(str(password)) if str(password or "") else "")
    profile.save()
    if str(mail or "").strip():
        set_mail(profile, mail)
    return profile


def delete(profile):
    """Удалить учётку (рабочую учётку игрока — нельзя)."""
    if profile.user_id is not None:
        raise EditError(f"{account_key(profile)} — рабочая учётка игрока, её не удалить")
    profile.delete()
