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
from world.models import WorldContribution, WorldCounter, WorldEvent, WorldFlag, WorldTrigger

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ATOM = re.compile(r"^world:([a-z0-9][a-z0-9_-]{0,63})(?:(>=|<=|>|<|=)(-?\d+))?$")
DEPTH = 8
ACTIONS = ("flag", "unflag", "count", "news", "air", "letter", "forum")


class WorldError(ValueError):
    pass


def check_name(name):
    name = (name or "").strip().lower()
    if not NAME.match(name):
        raise WorldError("Имя: латинские буквы в нижнем регистре, цифры, «-» и «_», до 64 знаков.")
    return name


# ---------- чтение ----------

def _load():
    return {
        "flags": set(WorldFlag.objects.filter(on=True).values_list("name", flat=True)),
        "counters": dict(WorldCounter.objects.values_list("name", "value")),
    }


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
        from air.radio import callsign_of

        try:
            return f"{source} · {callsign_of(user).name}" if source else callsign_of(user).name
        except Exception:                                   # noqa: BLE001 — позывной не обязателен для журнала
            return source or user.get_username()
    return source


# ---------- изменения ----------

def set_flag(name, on=True, source="", user=None, _depth=0):
    """Поставить или снять метку. Возвращает True, если что-то поменялось."""
    name = check_name(name)
    flag, _ = WorldFlag.objects.get_or_create(name=name)
    if flag.on == on:
        return False
    flag.on, flag.changed_at, flag.changed_by = on, timezone.now(), _who(source, user)[:200]
    flag.save(update_fields=["on", "changed_at", "changed_by"])
    _log("flag", name, f"метка world:{name} {'поставлена' if on else 'снята'}", source, user)
    forget()
    evaluate(_depth)
    return True


def count(name, delta=1, source="", user=None, _depth=0):
    """Вклад в счётчик. В режиме «каждый игрок один раз» повторный вклад игрока ничего не меняет. Возвращает новое значение."""
    name = check_name(name)
    counter, _ = WorldCounter.objects.get_or_create(name=name)
    with transaction.atomic():
        if counter.mode == WorldCounter.Mode.PLAYERS:
            if user is None or WorldContribution.objects.filter(counter=counter, user=user).exists():
                return counter.value
            delta = 1
        WorldContribution.objects.create(counter=counter, user=user, delta=delta, source=source[:200])
        WorldCounter.objects.filter(pk=counter.pk).update(value=F("value") + delta, changed_at=timezone.now())
    counter.refresh_from_db()
    _log("counter", name, f"world:{name} {delta:+d} → {counter.value}", _who(source, user), user)
    forget()
    evaluate(_depth)
    return counter.value


def set_counter(name, value, source="", user=None):
    """Задать значение (автор с пульта): записывается вкладом на разницу."""
    name = check_name(name)
    counter, _ = WorldCounter.objects.get_or_create(name=name)
    delta = int(value) - counter.value
    if not delta:
        return counter.value
    WorldContribution.objects.create(counter=counter, user=user, delta=delta, source=source[:200])
    WorldCounter.objects.filter(pk=counter.pk).update(value=int(value), changed_at=timezone.now())
    _log("counter", name, f"world:{name} задан {int(value)}", source, user)
    forget()
    evaluate()
    return int(value)


# ---------- триггеры ----------

def _truth(condition):
    from secure.access import satisfied

    return bool(condition) and satisfied(condition, frozenset())


def evaluate(_depth=0):
    """Проверить триггеры после изменения мира. Срабатывание на переходе условия в «верно»."""
    if _depth >= DEPTH:
        _log("trigger", "", "цепочка триггеров слишком длинная: остановлена", "мир")
        return
    for trigger in WorldTrigger.objects.filter(active=True):
        trigger.refresh_from_db(fields=["was_true", "fired_count"])     # вложенная проверка могла уже обработать его
        now = _truth(trigger.condition)
        if now == trigger.was_true:
            continue
        WorldTrigger.objects.filter(pk=trigger.pk).update(was_true=now)
        if now and (trigger.repeat or not trigger.fired_count):
            fire(trigger, _depth + 1)


def fire(trigger, _depth=0, by="", user=None):
    """Выполнить действия триггера (по условию или «запустить сейчас» с пульта)."""
    WorldTrigger.objects.filter(pk=trigger.pk).update(fired_at=timezone.now(), fired_count=F("fired_count") + 1)
    _log("trigger", trigger.name, f"сработал триггер {trigger.name}" + (f" ({trigger.label})" if trigger.label else ""), by or "условие", user)
    source = f"триггер {trigger.name}"
    for action in trigger.actions or []:
        run_action(action, source, _depth)


def run_action(action, source, _depth=0, user=None):
    """Одно действие мира: из триггера или из исхода письма и ответчика (тогда user — игрок)."""
    do = action.get("do")
    try:
        if do == "flag":
            set_flag(action.get("name", ""), True, source, user, _depth)
        elif do == "unflag":
            set_flag(action.get("name", ""), False, source, user, _depth)
        elif do == "count":
            count(action.get("name", ""), int(action.get("delta") or 1), source, user, _depth)
        elif do == "news":
            _news(action, source)
        elif do == "air":
            _air(action, source)
        elif do == "letter":
            _letter(action, source)
        elif do == "forum":
            _forum(action, source, user)
    except (WorldError, ValueError) as error:
        _log("action", do or "", f"действие не выполнено: {error}", source)


def _news(action, source):
    from news.models import Post

    title = (action.get("title") or "").strip()
    if not title:
        raise WorldError("у новости нет заголовка")
    values = {"title": title[:200], "body": action.get("text", ""), "publish_at": timezone.now(), "important": bool(action.get("important")),
              "byline": (action.get("byline") or "")[:60]}
    Post.objects.create(**values)
    _log("action", "news", f"новость «{title}»", source)


def _air(action, source):
    from air import radio
    from air.models import Station

    station = Station.objects.filter(name=(action.get("station") or "").upper()).first()
    if station is None:
        raise WorldError(f"нет станции {action.get('station')}")
    radio.station_transmit(station, action.get("freq", ""), action.get("text", ""), key=action.get("key", ""))
    _log("action", "air", f"{station.name} в эфире {action.get('freq')}", source)


def _letter(action, source):
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
    """Проблемы действий для Студии: [текст]."""
    out = []
    for number, action in enumerate(actions or [], 1):
        do = action.get("do")
        if do not in ACTIONS:
            out.append(f"действие {number}: неизвестно «{do}»")
        elif do in ("flag", "unflag", "count"):
            try:
                check_name(action.get("name", ""))
            except WorldError as error:
                out.append(f"действие {number}: {error}")
        elif do == "news" and not (action.get("title") or "").strip():
            out.append(f"действие {number}: у новости нет заголовка")
        elif do == "air" and not (action.get("station") and action.get("freq") and (action.get("text") or "").strip()):
            out.append(f"действие {number}: нужны станция, частота и текст")
        elif do == "forum":
            from forum.models import Section

            if not Section.objects.filter(pk=action.get("section") or 0, archived=False).exists():
                out.append(f"действие {number}: нет раздела форума")
            elif not (action.get("text") or "").strip():
                out.append(f"действие {number}: у записи нет текста")
            elif not (action.get("title") or "").strip():
                out.append(f"действие {number}: нужен заголовок темы")
            elif action.get("mode", "new") not in ("new", "append"):
                out.append(f"действие {number}: режим new или append")
            elif action.get("character"):
                from characters.models import Character

                if not Character.objects.filter(code=str(action["character"]).upper()).exists():
                    out.append(f"действие {number}: нет персонажа {action['character']}")
        elif do == "letter":
            from filesystem.models import Item

            if not Item.objects.filter(slug=action.get("item", "")).exists():
                out.append(f"действие {number}: нет письма «{action.get('item', '')}»")
    return out


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
