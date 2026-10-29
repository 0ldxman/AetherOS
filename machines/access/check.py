"""Проверка входа «всухую» для автора: пустит ли запись, и по каким шагам это решено.

Те же правила, что у входа игрока (machines/access/entry.py и machines/network/bridge.py): блокировка, откуда, через что, когда,
затем токен или пароль с ключами по режиму политики. Ничего не пишется: ни событий, ни расхода токена, ни блокировки. Пароль, ключи и
токен необязательны: без них способы входа только перечисляются, а не проверяются.
"""
from dataclasses import dataclass, field
from datetime import datetime

from machines.access import entry, windows
from machines.models import EntryPolicy, LoginEvent, SystemType


@dataclass
class Step:
    name: str                   # policy | lock | source | route | window | token | key | password
    ok: bool | None             # None: шаг не проверялся (нечего проверять или не дали данных)
    text: str


@dataclass
class Verdict:
    admitted: bool | None       # None: правила пропускают, а способы входа не проверялись
    kind: str                   # LoginEvent.Kind отказа или "ok"
    steps: list[Step] = field(default_factory=list)


def origin_of(profile):
    """(откуда политика, политика): profile, machine, system или (None, None)."""
    if profile.entry_policy_id:
        return "profile", profile.entry_policy
    machine = profile.machine
    if machine.entry_policy_id:
        return "machine", machine.entry_policy
    system = SystemType.objects.filter(code=machine.system).select_related("entry_policy").first()
    if system is not None and system.entry_policy_id:
        return "system", system.entry_policy
    return None, None


ORIGIN_TEXT = {"profile": "у учётки", "machine": "у машины", "system": "у типа системы"}


def check(profile, *, source="", chain=(), at=None, player=None, password=None, keys=(), token=None):
    """Verdict входа на запись profile. source: имя хоста, откуда входят; chain: хосты цепочки мостов (по умолчанию только source);
    at: время на машине (по умолчанию сейчас по её часам для player); player: игрок, для которого смотреть блокировки."""
    from machines.network import bridge

    steps = []
    origin, policy = origin_of(profile)
    if policy is None:
        steps.append(Step("policy", None, "Политики нет: ограничений по месту и времени нет."))
    else:
        steps.append(Step("policy", None, f"Политика «{policy.name}» {ORIGIN_TEXT[origin]}."))

    def refuse(kind):
        return Verdict(False, kind, steps)

    if player is not None:
        wait = max(bridge.locked_for(player, profile), entry.locked_seconds(player, profile) if policy else 0)
        if wait:
            steps.append(Step("lock", False, f"Игрок заблокирован на этой учётке ещё {wait // 60}:{wait % 60:02d}."))
            return refuse(LoginEvent.Kind.LOCKED)
        steps.append(Step("lock", True, "Игрок не заблокирован."))

    if policy is not None:
        sources = EntryPolicy.lines(policy.sources)
        if sources:
            if not entry.host_matches(source, sources):
                steps.append(Step("source", False, f"Источник «{source or '—'}» не подходит под {', '.join(sources)}."))
                return refuse(LoginEvent.Kind.SOURCE)
            steps.append(Step("source", True, f"Источник «{source}» подходит под {', '.join(sources)}."))
        via = EntryPolicy.lines(policy.via)
        if via:
            route = list(chain) or [source]
            missing = [host for host in via if not entry.host_matches_any(host, route)]
            if missing:
                steps.append(Step("route", False, f"Вход не идёт через {', '.join(missing)} (цепочка: {' → '.join(route) or '—'})."))
                return refuse(LoginEvent.Kind.ROUTE)
            steps.append(Step("route", True, f"Цепочка проходит через {', '.join(via)}."))
        if policy.windows.strip():
            moment = at or entry.machine_now(profile.machine, player)
            if not windows.allows(windows.parse(policy.windows), moment):
                steps.append(Step("window", False, f"{_moment(moment)} вне окна «{_one_line(policy.windows)}»."))
                return refuse(LoginEvent.Kind.WINDOW)
            steps.append(Step("window", True, f"{_moment(moment)} внутри окна «{_one_line(policy.windows)}»."))

    if token:
        if bridge.valid_token(profile, token) is None:
            steps.append(Step("token", False, "Токен не найден, просрочен или исчерпан."))
            return refuse(LoginEvent.Kind.BAD_TOKEN)
        steps.append(Step("token", True, "Токен действует: пароль и ключи не нужны."))
        return Verdict(True, "ok", steps)

    need_password, need_key = bridge.password_required(profile), bridge.key_required(profile)
    either = entry.mode_of(profile) == EntryPolicy.Mode.ANY and need_password and need_key
    if not need_password and not need_key:
        steps.append(Step("password", True, "У учётки нет ни пароля, ни ключа: войти может любой."))
        return Verdict(True, "ok", steps)

    rule = "пароль или ключ" if either else " и ".join(word for word, needed in (("пароль", need_password), ("ключ", need_key)) if needed)
    if password is None and not keys:
        steps.append(Step("mode", None, f"Нужно: {rule}. Введите пароль или ключи, чтобы проверить их."))
        return Verdict(None, "ok", steps)

    key_ok = bridge.keys_ok(profile, keys)
    password_ok = password is not None and bridge.password_ok(profile, password)
    if need_key:
        steps.append(Step("key", key_ok, "Ключи подходят." if key_ok else "Ключей не хватает."))
    if need_password:
        steps.append(Step("password", password_ok if password is not None else None,
                          "Пароль не введён." if password is None else ("Пароль верный." if password_ok else "Пароль неверный.")))
    if either:
        admitted = key_ok or password_ok
    else:
        admitted = (key_ok or not need_key) and (password_ok or not need_password)
    steps.append(Step("mode", admitted, f"Нужно: {rule}."))
    if admitted:
        return Verdict(True, "ok", steps)
    return refuse(LoginEvent.Kind.BAD_PASSWORD if need_password and not password_ok else LoginEvent.Kind.BAD_KEY)


def _moment(moment: datetime):
    days = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
    return f"{days[moment.weekday()]} {moment:%H:%M}"


def _one_line(text):
    return "; ".join(line.strip() for line in text.splitlines() if line.strip())
