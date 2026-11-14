"""Правила на события: событие с подходящими подробностями + условие на факты игрока → действия движка.

Кратность: world — один раз в мире (первый игрок; это и есть «кто первым»), player — раз на игрока, always — каждый раз.
Действия выполняются от имени игрока события: доступны мир, его метки и его учётка (если событие было на машине).
Эффекты браузера (alert, open) правилу недоступны: события приходят не из живого окна.
Действия правил сами шлют события (метка мира, ключ): глубина цепочки ограничена.
"""
import contextvars
import fnmatch

from django.db import transaction

from engine.models import Rule, RuleFire

DEPTH = 8
_depth = contextvars.ContextVar("engine_rule_depth", default=0)


def matches(rule, event):
    """Подробности события подходят под образец правила: каждое поле равно (или подходит по * для строк)."""
    data = {**(event.data or {}), "host": event.host, "login": event.login}
    for key, wanted in (rule.match or {}).items():
        have = data.get(key)
        if isinstance(have, bool) or isinstance(wanted, bool):
            if str(have).lower() != str(wanted).lower():
                return False
            continue
        have, wanted = "" if have is None else str(have), str(wanted)
        if not (fnmatch.fnmatchcase(have, wanted) if any(ch in wanted for ch in "*?[") else have == wanted):
            return False
    return True


def _box(event):
    """Учётка игрока, на которой случилось событие (для ключей, файлов, писем)."""
    if event.user is None or not event.host or not event.login:
        return None
    from machines.models import MachineProfile
    from mail.boxes import Box

    profile = MachineProfile.objects.select_related("machine").filter(machine__hostname=event.host, login=event.login).first()
    return Box.of_profile(profile, event.user) if profile is not None else None


def _facts(event, box):
    from engine import facts
    from filesystem import keystore

    keys = [slug for _, slug in keystore.held(box.view, box.machine, box.login)] if box is not None else []
    return facts.of(event.user, keys)


def _due(rule, user):
    if rule.once == Rule.Once.WORLD:
        return not rule.fires.exists()
    if rule.once == Rule.Once.PLAYER:
        return user is not None and not rule.fires.filter(user=user).exists()
    return True


def dispatch(event):
    """Проверить правила на событие. Возвращает число сработавших."""
    depth = _depth.get()
    if depth >= DEPTH:
        return 0
    rules = [rule for rule in Rule.objects.filter(active=True, on=event.name) if matches(rule, event)]
    if not rules:
        return 0
    from engine import actions as engine
    from engine.context import Ctx
    from secure.access import satisfied

    box = _box(event)
    known = _facts(event, box) if any(rule.condition for rule in rules) else frozenset()
    fired = 0
    token = _depth.set(depth + 1)
    try:
        for rule in rules:
            with transaction.atomic():
                Rule.objects.select_for_update().filter(pk=rule.pk).first()        # два игрока одновременно: «первым» будет один
                if not _due(rule, event.user):
                    continue
                if rule.condition and not satisfied(rule.condition, known):
                    continue
                RuleFire.objects.create(rule=rule, user=event.user, event=event)
            engine.run(rule.actions, Ctx(source=f"правило {rule.name}", user=event.user, box=box, depth=depth + 1))
            fired += 1
    finally:
        _depth.reset(token)
    return fired


def first(rule):
    """Кто сработал первым: (игрок, когда) или None."""
    found = rule.fires.select_related("user").first()
    return (found.user, found.at) if found is not None else None
