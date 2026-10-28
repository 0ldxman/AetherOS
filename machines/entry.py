"""Решение о входе на запись: политика, блокировка после ошибок, откуда и в какое время можно.

Политика (EntryPolicy) назначается типу системы, машине или профилю, действует самая конкретная. Профиль перекрывает политику своими
ttl, cooldown и kick_message, если они заполнены. Пароль, ключи и токены остаются у профиля (machines/bridge.py), здесь только то,
что вокруг них: кто, откуда, когда, сколько раз ошибся. Каждое событие пишется в LoginEvent: из него считается блокировка, и это же
журнал хоста для игрока (filesystem/sources/log.py).
"""
import fnmatch
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from machines import windows
from machines.models import EntryPolicy, LoginEvent, SystemType

KEEP = timedelta(days=30)


@dataclass
class Decision:
    """Отказ: kind это LoginEvent.Kind (причина), text заменяет стандартный текст, wait секунд до повтора (для блокировки)."""

    kind: str
    text: str = ""
    wait: int = 0


def policy_of(profile):
    """Действующая политика записи или None (ограничений нет)."""
    machine = profile.machine
    if profile.entry_policy_id:
        return profile.entry_policy
    if machine.entry_policy_id:
        return machine.entry_policy
    system = SystemType.objects.filter(code=machine.system).select_related("entry_policy").first()
    return system.entry_policy if system is not None else None


def ttl_of(profile):
    policy = policy_of(profile)
    return profile.ttl if profile.ttl is not None else (policy.ttl if policy else None)


def lock_seconds_of(profile):
    """На сколько запись замирает после обрыва по сроку (None: не замирает)."""
    policy = policy_of(profile)
    return profile.cooldown if profile.cooldown is not None else (policy.lock_seconds if policy else None)


def kick_text_of(profile):
    policy = policy_of(profile)
    return profile.kick_message.strip() or (policy.kick_text.strip() if policy else "")


def mode_of(profile):
    policy = policy_of(profile)
    return policy.mode if policy else EntryPolicy.Mode.ALL


def machine_now(machine, user=None):
    """Время на машине для этого игрока. Пока это мировое время; свои часы машины подключатся здесь."""
    return timezone.localtime()


def locked_seconds(user, profile):
    """Сколько секунд запись ещё не принимает игрока из-за серии ошибок (0: принимает)."""
    policy = policy_of(profile)
    if policy is None or not policy.max_attempts:
        return 0
    last = LoginEvent.objects.filter(profile=profile, user=user, kind=LoginEvent.Kind.LOCKED).order_by("-at").first()
    if last is None:
        return 0
    return max(0, int((last.at + timedelta(seconds=policy.lock_seconds) - timezone.now()).total_seconds()) + 1)


def record(profile, user, kind, source="", detail=""):
    """Записать событие входа и убрать старое."""
    event = LoginEvent.objects.create(profile=profile, user=user, kind=kind, source=source, detail=detail)
    LoginEvent.objects.filter(profile=profile, user=user, at__lt=timezone.now() - KEEP).delete()
    return event


def after_failure(profile, user, source=""):
    """Неверный пароль или ключ уже записан. True, если эта ошибка включила блокировку."""
    policy = policy_of(profile)
    if policy is None or not policy.max_attempts:
        return False
    since = timezone.now() - timedelta(seconds=policy.attempts_window)
    marks = LoginEvent.objects.filter(profile=profile, user=user, kind__in=(LoginEvent.Kind.OK, LoginEvent.Kind.LOCKED)).order_by("-at").first()
    failures = LoginEvent.objects.filter(profile=profile, user=user, kind__in=LoginEvent.FAILURES, at__gte=since)
    if marks is not None:
        failures = failures.filter(at__gt=marks.at)
    if failures.count() >= policy.max_attempts:
        record(profile, user, LoginEvent.Kind.LOCKED, source, f"{policy.max_attempts} failed attempts")
        return True
    return False


def host_matches(name, patterns):
    return any(fnmatch.fnmatchcase(name or "", pattern) for pattern in patterns)


def gate(profile, user, source_machine, chain):
    """Проверки до способов входа: блокировка, откуда, через что, когда. Decision отказа или None.

    source_machine это машина, с которой входят; chain это имена хостов цепочки мостов игрока от исходной машины до неё."""
    from machines import bridge

    source = source_machine.hostname or source_machine.name
    wait = bridge.locked_for(user, profile)
    policy = policy_of(profile)
    if policy is not None:
        wait = max(wait, locked_seconds(user, profile))
    if wait:
        return Decision(LoginEvent.Kind.LOCKED, policy.locked_text.strip() if policy else "", wait)
    if policy is None:
        return None
    sources = EntryPolicy.lines(policy.sources)
    if sources and not host_matches(source, sources):
        return Decision(LoginEvent.Kind.SOURCE, policy.denied_text.strip())
    via = EntryPolicy.lines(policy.via)
    if via and not all(host_matches_any(host, chain) for host in via):
        return Decision(LoginEvent.Kind.ROUTE, policy.denied_text.strip())
    if policy.windows.strip() and not windows.allows(windows.parse(policy.windows), machine_now(profile.machine, user)):
        return Decision(LoginEvent.Kind.WINDOW, policy.window_text.strip())
    return None


def host_matches_any(pattern, chain):
    return any(fnmatch.fnmatchcase(name or "", pattern) for name in chain)
