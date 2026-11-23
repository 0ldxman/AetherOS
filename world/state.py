"""Общий мир: метки, счётчики, триггеры. Одно состояние на всех игроков.

Условия (secure.access.satisfied) понимают строки:
    world:core-online        метка стоит
    world:fragments>=7       счётчик; сравнения >=, >, <=, <, =
Состояние читается один раз за запрос. Любое изменение метки или счётчика проверяет триггеры: срабатывание на переходе
условия из «неверно» в «верно»; действия триггера могут менять мир дальше (цепочки), глубина ограничена.
"""
import re

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from machines import memo
from world.models import WorldEvent, WorldTrigger

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ATOM = re.compile(r"^world:([a-z0-9][a-z0-9_-]{0,63})(?:(>=|<=|>|<|=)(-?\d+))?$")
DEPTH = 8


class WorldError(ValueError):
    pass


def check_name(name):
    name = (name or "").strip().lower()
    if not NAME.match(name):
        raise WorldError("Имя: латинские буквы в нижнем регистре, цифры, «-» и «_», до 64 знаков.")
    return name


# ---------- чтение ----------

def _load():
    from engine.models import Value

    rows = list(Value.objects.filter(owner="world", owner_id=0, user=None).values_list("kind", "name", "value"))
    return {"flags": {name for kind, name, value in rows if kind == "tag" and value},
            "counters": {name: value for kind, name, value in rows if kind == "count"}}


def names(kind):
    """Имена меток (tag) или счётчиков (count) мира, заведённых значением или описанием."""
    from engine.models import Value, ValueInfo

    found = set(Value.objects.filter(kind=kind, owner="world", owner_id=0, user=None).values_list("name", flat=True))
    return sorted(found | set(ValueInfo.objects.filter(kind=kind, owner="world", owner_id=0).values_list("name", flat=True)))


def snapshot():
    return memo.cached(("world-state",), _load)


def forget():
    memo.forget(("world-state",))


def is_atom(text):
    return isinstance(text, str) and text.startswith("world:")


def parse_atom(text):
    """(имя, оператор или None, число или None); WorldError, если строка не похожа на world:имя[оп число]."""
    found = ATOM.match((text or "").strip())
    if not found:
        raise WorldError(f"«{text}»: пишите world:имя или world:счётчик>=число")
    name, op, number = found.groups()
    return name, op, int(number) if number is not None else None


def atom(text):
    """Верна ли строка world:… сейчас. Непонятная строка закрывает, как и неизвестное условие."""
    try:
        name, op, number = parse_atom(text)
    except WorldError:
        return False
    state = snapshot()
    if op is None:
        return name in state["flags"]
    value = state["counters"].get(name, 0)
    return {">=": value >= number, ">": value > number, "<=": value <= number, "<": value < number, "=": value == number}[op]


def atoms_in(condition):
    """Все строки world:… в условии (для пульта: пороги счётчиков, какие метки нужны)."""
    if isinstance(condition, str):
        return [condition] if is_atom(condition) else []
    if isinstance(condition, dict):
        found = []
        for value in condition.values():
            for part in value if isinstance(value, list) else [value]:
                found += atoms_in(part)
        return found
    return []


def thresholds(counter_name):
    """Пороги, на которые проверяется счётчик в триггерах: [(число, оператор, имя триггера)]."""
    found = []
    for trigger in WorldTrigger.objects.all():
        for text in atoms_in(trigger.condition):
            try:
                name, op, number = parse_atom(text)
            except WorldError:
                continue
            if name == counter_name and op is not None:
                found.append((number, op, trigger.name))
    return sorted(found)


# ---------- журнал ----------

def _log(kind, subject, text, source="", user=None):
    WorldEvent.objects.create(kind=kind, subject=subject, text=text[:400], source=source[:200], user=user)


def _who(source, user):
    if user is not None:
        from air.radio import account_of, callsign_of

        try:
            name = callsign_of(account_of(user)).name
            return f"{source} · {name}" if source else name
        except Exception:                                   # noqa: BLE001 — позывной не обязателен для журнала
            return source or user.get_username()
    return source


# ---------- изменения ----------

def set_flag(name, on=True, source="", user=None, _depth=0):
    """Поставить или снять метку мира. Возвращает True, если что-то поменялось."""
    from engine import values

    return values.set_tag(values.WORLD, 0, check_name(name), on, source=source, actor=user, _depth=_depth)


def count(name, delta=1, source="", user=None, _depth=0):
    """Прибавить к счётчику мира. Возвращает новое значение."""
    from engine import values

    return values.add(values.WORLD, 0, check_name(name), int(delta), source=source, actor=user, _depth=_depth)


def set_counter(name, value, source="", user=None):
    """Задать значение счётчика мира (автор с пульта)."""
    from engine import values

    return values.put(values.WORLD, 0, check_name(name), int(value), source=source, actor=user)


# ---------- триггеры ----------

def _truth(condition):
    from secure.access import satisfied

    return bool(condition) and satisfied(condition, frozenset())


def evaluate(_depth=0):
    """Проверить триггеры после изменения мира. Срабатывание на переходе условия в «верно»."""
    if _depth >= DEPTH:
        _log("trigger", "", "цепочка триггеров слишком длинная: остановлена", "мир")
        return
    for pk in list(WorldTrigger.objects.filter(active=True).values_list("pk", flat=True)):
        go = None
        with transaction.atomic():                   # переход «ложь → правда» под блокировкой: два процесса не сработают оба
            trigger = WorldTrigger.objects.select_for_update().filter(pk=pk, active=True).first()
            if trigger is None:
                continue
            now = _truth(trigger.condition)
            if now == trigger.was_true:
                continue
            WorldTrigger.objects.filter(pk=trigger.pk).update(was_true=now)
            if now and (trigger.repeat or not trigger.fired_count):
                go = trigger
        if go is not None:
            fire(go, _depth + 1)


def fire(trigger, _depth=0, by="", user=None):
    """Выполнить действия триггера (по условию или «запустить сейчас» с пульта)."""
    WorldTrigger.objects.filter(pk=trigger.pk).update(fired_at=timezone.now(), fired_count=F("fired_count") + 1)
    _log("trigger", trigger.name, f"сработал триггер {trigger.name}" + (f" ({trigger.label})" if trigger.label else ""), by or "условие", user)
    from engine import actions as engine
    from engine.context import Ctx

    engine.run(trigger.actions, Ctx(source=f"триггер {trigger.name}", depth=_depth))      # у триггера нет игрока: только действия мира


def _news(action, source, user=None):
    from news.models import Post

    title = (action.get("title") or "").strip()
    if not title:
        raise WorldError("у новости нет заголовка")
    values = {"title": title[:200], "body": action.get("text", ""), "publish_at": timezone.now(), "important": bool(action.get("important")),
              "byline": (action.get("byline") or "")[:60]}
    Post.objects.create(**values)
    _log("action", "news", f"новость «{title}»", source)


def _air(action, source, user=None):
    from air import radio
    from air.models import Station

    station = Station.objects.filter(name=(action.get("station") or "").upper()).first()
    if station is None:
        raise WorldError(f"нет станции {action.get('station')}")
    radio.station_transmit(station, action.get("freq", ""), action.get("text", ""), key=action.get("key", ""))
    _log("action", "air", f"{station.name} в эфире {action.get('freq')}", source)


def _letter(action, source, user=None):
    from filesystem.models import Item
    from world import letters

    item = Item.objects.filter(slug=action.get("item", "")).first()
    if item is None:
        raise WorldError(f"нет письма {action.get('item')}")
    split = lambda text: [part.strip() for part in (text or "").split(",") if part.strip()]     # noqa: E731
    letters.send_all(item, split(action.get("systems")), split(action.get("machines")), source)
    _log("action", "letter", f"письмо всем: {item.slug}", source)


class _Keep(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def fill(text, user=None):
    """Подстановки в тексте действия: {world_<счётчик>}, {time} (игровое время), {player} (позывной игрока, если действие от игрока)."""
    from machines.world import chrono

    values = _Keep(params())
    values["time"] = chrono.stamp(timezone.now())
    if user is not None:
        values["player"] = _who("", user)
    try:
        return (text or "").format_map(values)
    except (ValueError, IndexError):
        return text or ""


def _forum(action, source, user=None):
    from characters.models import Character
    from forum import logic
    from forum.models import Section

    section = Section.objects.filter(pk=action.get("section") or 0, archived=False).first()
    if section is None:
        raise WorldError(f"нет раздела форума {action.get('section')}")
    character = None
    if action.get("character"):
        character = Character.objects.filter(code=str(action["character"]).upper()).first()
        if character is None:
            raise WorldError(f"нет персонажа {action['character']}")
    try:
        post = logic.world_post(section, fill(action.get("text"), user), fill(action.get("title"), user), action.get("mode") or "new",
                                character, action.get("name") or "")
    except logic.ForumError as error:
        raise WorldError(str(error)) from None
    _log("action", "forum", f"форум: «{post.topic.title}»", source)


def check_actions(actions):
    """Проблемы действий триггера для Студии: только действия мира (engine/actions.py)."""
    from engine import actions as engine

    return engine.check(actions)


def check_condition(condition):
    from django.core.exceptions import ValidationError

    from secure.access import validate_requirements

    if not condition:
        return ["условие пустое"]
    try:
        validate_requirements(condition)
    except ValidationError as error:
        return [" ".join(error.messages)]
    texts = atoms_in(condition)
    if not texts:
        return ["в условии нет ни одной строки world:…"]
    out = []
    for text in texts:
        try:
            parse_atom(text)
        except WorldError as error:
            out.append(str(error))
    return out


def params():
    """Подстановки для текстов: {world_<счётчик>} — значение, дефисы в имени становятся «_»."""
    return {f"world_{name.replace('-', '_')}": value for name, value in snapshot()["counters"].items()}
