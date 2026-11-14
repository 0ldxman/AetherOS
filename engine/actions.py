"""Единый словарь действий. Каждое действие описано здесь один раз: что ему нужно, какие у него поля, как оно проверяется,
что выдаёт или трогает и как выполняется. Почта, ответчики эфира, триггеры мира и кукловод зовут run(); Студия рисует
формы по catalog(). Хранение прежнее: список словарей {"do": имя, ...поля}.

Что нужно действию (needs): world — ничего, работает откуда угодно; user — игрок; account — учётка игрока на машине;
session — живой браузер; host — действие хозяина (шаг переписки, возврат письма), выполняет сам хозяин через ctx.host.
"""
from dataclasses import dataclass, field

from engine.context import ACCOUNT, SESSION, USER, WORLD, Ctx

HOST = "host"


class ActionError(ValueError):
    """Действие нельзя выполнить: понятный автору текст."""


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"      # text, textarea, number, bool, key, item, letter, flag, world_flag, counter, section, character, station, step, path, select
    placeholder: str = ""
    required: bool = False
    options: tuple = ()     # для select: ((значение, подпись), ...)


@dataclass(frozen=True)
class Spec:
    name: str
    label: str
    needs: str
    group: str
    summary: str                         # как действие выглядит в списке: шаблон с {поле}
    fields: tuple = ()
    run: object = None                   # функция(action, ctx); у действий хозяина None
    check: object = None                 # функция(action) -> [текст]
    refs: object = None                  # функция(action) -> [(вид, имя, роль)]: роль grants (выдаёт) или touches (меняет)


REGISTRY = {}


def register(spec):
    REGISTRY[spec.name] = spec
    return spec


# ---------- выполнение ----------

def _log_failure(do, error, ctx):
    from world import state

    state._log("action", do or "", f"действие не выполнено: {error}", ctx.source)


def run(actions, ctx=None):
    """Выполнить действия по порядку. Неизвестное, недоступное в этом контексте или сломанное действие пропускается и
    пишется в журнал мира; остальные выполняются. Возвращает эффекты для браузера (ctx.effects)."""
    ctx = ctx or Ctx()
    have = ctx.provides()
    for action in actions or []:
        do = (action or {}).get("do")
        if do in ctx.host:
            ctx.host[do](action, ctx)
            continue
        spec = REGISTRY.get(do)
        if spec is None or spec.run is None:
            _log_failure(do, f"неизвестное действие «{do}»", ctx)
            continue
        if spec.needs not in have:
            if spec.needs != SESSION:                # эффекты браузера без браузера молча не нужны
                _log_failure(do, f"«{spec.label}» здесь недоступно: нет {_NEED_TEXT[spec.needs]}", ctx)
            continue
        try:
            spec.run(action, ctx)
        except (ActionError, ValueError) as error:
            _log_failure(do, str(error), ctx)
    return ctx.effects


_NEED_TEXT = {USER: "игрока", ACCOUNT: "учётки игрока", SESSION: "браузера игрока", HOST: "хозяина"}


def check(actions, provides=(WORLD,), host=()):
    """Проблемы списка для Студии: [текст]. provides — что даёт место (world, user, account, session), host — его локальные действия."""
    out = []
    for number, action in enumerate(actions or [], 1):
        do = (action or {}).get("do")
        spec = REGISTRY.get(do)
        where = f"действие {number}"
        if spec is None:
            out.append(f"{where}: неизвестно «{do}»")
            continue
        if (spec.needs == HOST and do not in host) or (spec.needs != HOST and spec.needs not in provides):
            out.append(f"{where}: «{spec.label}» здесь недоступно")
            continue
        for item in spec.fields:
            if item.required and action.get(item.name) in (None, ""):
                out.append(f"{where}: не заполнено «{item.label}»")
                break
        else:
            out += [f"{where}: {text}" for text in (spec.check(action) if spec.check else [])]
    return out


def refs(actions):
    """Что выдают и трогают действия: [(вид, имя, роль)]. Для карты связей."""
    out = []
    for action in actions or []:
        spec = REGISTRY.get((action or {}).get("do"))
        if spec is not None and spec.refs is not None:
            out += spec.refs(action)
    return out


def catalog():
    """Описание всех действий для Студии."""
    return [{"name": s.name, "label": s.label, "needs": s.needs, "group": s.group, "summary": s.summary,
             "fields": [{"name": f.name, "label": f.label, "kind": f.kind, "placeholder": f.placeholder, "required": f.required,
                         "options": [{"value": v, "label": label} for v, label in f.options]} for f in s.fields]}
            for s in REGISTRY.values()]


# ---------- общие проверки ----------

def _item(slug, fmt=None):
    from filesystem.models import Item

    found = Item.objects.filter(slug=slug or "")
    if fmt:
        found = found.filter(format=fmt)
    return found.first()


def _need_item(action, name, fmt=None, what="объекта"):
    return [] if _item(action.get(name), fmt) is not None else [f"нет {what} «{action.get(name) or '?'}»"]


def _world_name(action):
    from world import state

    try:
        state.check_name(action.get("name", ""))
        return []
    except state.WorldError as error:
        return [str(error)]


# ---------- игрок: личные метки ----------

def _flag(action, ctx):
    from mail.models import Flag

    name = (action.get("name") or "").strip()
    if not name:
        raise ActionError("метка без имени")
    Flag.objects.get_or_create(user=ctx.user, name=name)


def _unflag(action, ctx):
    from mail.models import Flag

    Flag.objects.filter(user=ctx.user, name=(action.get("name") or "").strip()).delete()


register(Spec("flag", "Поставить метку игрока", USER, "Игрок", "метка {name}", (Field("name", "Метка", "flag", "dock-open", True),),
              run=_flag, refs=lambda a: [("flag", a.get("name", ""), "grants")]))
register(Spec("unflag", "Снять метку игрока", USER, "Игрок", "снять метку {name}", (Field("name", "Метка", "flag", "dock-open", True),),
              run=_unflag, refs=lambda a: [("flag", a.get("name", ""), "touches")]))


# ---------- учётка игрока: ключи, файлы, письма ----------

def _key(action, ctx):
    from filesystem import keystore
    from filesystem.models import KEY_FORMAT

    item = _item(action.get("slug"), KEY_FORMAT)
    if item is None:
        raise ActionError(f"нет ключа «{action.get('slug')}»")
    box = ctx.box
    if not keystore.secrets_dir(box.machine, box.login):
        raise ActionError(f"у учётки {box.login} нет папки секретов")
    keystore.put(box.view, box.machine, box.login, item)


def _file(action, ctx):
    from mail import letters

    item = _item(action.get("item"))
    if item is None:
        raise ActionError(f"нет объекта «{action.get('item')}»")
    path = letters.fill(action.get("path", ""), {"login": ctx.box.login})
    if not path.startswith("/"):
        raise ActionError("путь файла должен начинаться с «/»")
    ctx.box.view.put_item(path, item)


def _letter(action, ctx):
    item = _item(action.get("item"))
    if item is None:
        raise ActionError(f"нет письма «{action.get('item')}»")
    ctx.box.queue(item, int(action.get("delay") or 0))


def _key_check(action):
    from filesystem.models import KEY_FORMAT

    return _need_item(action, "slug", KEY_FORMAT, "ключа")


register(Spec("key", "Выдать ключ", ACCOUNT, "Игрок", "ключ {slug}", (Field("slug", "Ключ", "key", "", True),),
              run=_key, check=_key_check, refs=lambda a: [("key", a.get("slug", ""), "grants")]))
register(Spec("file", "Положить файл", ACCOUNT, "Игрок", "файл {item} → {path}",
              (Field("item", "Объект", "item", "", True), Field("path", "Путь", "path", "/home/{login}/file.txt", True)),
              run=_file, check=lambda a: _need_item(a, "item") + ([] if (a.get("path") or "").startswith("/") else ["путь должен начинаться с «/»"]),
              refs=lambda a: [("item", a.get("item", ""), "grants")]))
register(Spec("letter", "Прислать письмо", ACCOUNT, "Игрок", "письмо {item}",
              (Field("item", "Письмо", "letter", "", True), Field("delay", "Задержка, с", "number", "0")),
              run=_letter, check=lambda a: _need_item(a, "item", "msg", "письма"), refs=lambda a: [("item", a.get("item", ""), "grants")]))


# ---------- браузер игрока: эффекты ----------

def _effect(name, value, quoted=False):
    from filesystem.layers.compiler import parse_effect
    from filesystem.layers.parser import Action

    effect, error = parse_effect(Action(name=name, line=0, value=value, quoted=quoted))
    if error:
        raise ActionError(error)
    return effect


def _alert_value(action):
    return f"{action.get('message', '')} count={int(action.get('count') or 6)} gap={int(action.get('gap') or 500)}"


def _alert(action, ctx):
    ctx.effects.append(_effect("alert", _alert_value(action)))


def _open(action, ctx):
    ctx.effects.append(_effect("open", action.get("url", ""), quoted=True))


def _kick(action, ctx):
    from machines.network import bridge

    if ctx.profile is not None:
        bridge.request_kick(ctx.user, ctx.profile)


def _effect_check(name, value_of, quoted=False):
    def check_one(action):
        try:
            _effect(name, value_of(action), quoted)
            return []
        except ActionError as error:
            return [str(error)]
    return check_one


register(Spec("alert", "Засыпать окнами ошибок", SESSION, "Браузер", "окна ошибок {message}",
              (Field("message", "Сообщение", "text", "unreachable", True), Field("count", "Сколько окон", "number", "6"),
               Field("gap", "Пауза, мс", "number", "500")),
              run=_alert, check=_effect_check("alert", _alert_value)))
register(Spec("open", "Открыть окно", SESSION, "Браузер", "открыть {url}", (Field("url", "Адрес", "text", "apps/wiki/go/secret/", True),),
              run=_open, check=_effect_check("open", lambda a: a.get("url", ""), True)))
register(Spec("kick", "Выбросить из сессии", ACCOUNT, "Браузер", "выбросить с учётки", (), run=_kick))


# ---------- мир ----------

def _world_flag(on):
    def go(action, ctx):
        from world import state

        state.set_flag(action.get("name", ""), on, ctx.source, ctx.user, ctx.depth)
    return go


def _world_count(action, ctx):
    from world import state

    state.count(action.get("name", ""), int(action.get("delta") or 1), ctx.source, ctx.user, ctx.depth)


def _world(fn_name):
    def go(action, ctx):
        from world import state

        getattr(state, fn_name)(action, ctx.source, ctx.user)
    return go


def _section_check(action):
    from forum.models import Section

    out = [] if Section.objects.filter(pk=action.get("section") or 0, archived=False).exists() else ["нет раздела форума"]
    if action.get("mode", "new") not in ("new", "append"):
        out.append("режим new или append")
    if action.get("character"):
        from characters.models import Character

        if not Character.objects.filter(code=str(action["character"]).upper()).exists():
            out.append(f"нет персонажа {action['character']}")
    return out


def _station_check(action):
    from air.models import Station

    return [] if Station.objects.filter(name=(action.get("station") or "").upper()).exists() else [f"нет станции {action.get('station') or '?'}"]


register(Spec("world_flag", "Поставить метку мира", WORLD, "Мир", "поставить world:{name}", (Field("name", "Метка мира", "world_flag", "core-online", True),),
              run=_world_flag(True), check=_world_name, refs=lambda a: [("world", a.get("name", ""), "grants")]))
register(Spec("world_unflag", "Снять метку мира", WORLD, "Мир", "снять world:{name}", (Field("name", "Метка мира", "world_flag", "core-online", True),),
              run=_world_flag(False), check=_world_name, refs=lambda a: [("world", a.get("name", ""), "touches")]))
register(Spec("world_count", "Вклад в счётчик мира", WORLD, "Мир", "world:{name} +{delta}",
              (Field("name", "Счётчик", "counter", "fragments", True), Field("delta", "Сколько", "number", "1")),
              run=_world_count, check=_world_name, refs=lambda a: [("counter", a.get("name", ""), "grants")]))
register(Spec("news", "Опубликовать новость", WORLD, "Мир", "новость «{title}»",
              (Field("title", "Заголовок", "text", "", True), Field("text", "Текст", "textarea"), Field("byline", "Подпись", "text"),
               Field("important", "Важная: всплывает на столе", "bool")),
              run=_world("_news")))
register(Spec("air", "Передать в эфир", WORLD, "Мир", "{station} в эфир {freq}",
              (Field("station", "Станция", "station", "", True), Field("freq", "Частота, МГц", "text", "7.205", True),
               Field("text", "Текст", "textarea", "", True), Field("key", "Шифр", "text", "необязательно")),
              run=_world("_air"), check=_station_check))
register(Spec("letter_all", "Письмо всем", WORLD, "Мир", "письмо всем {item}",
              (Field("item", "Письмо", "letter", "", True), Field("machines", "Только машины", "text", "aether-main, …"),
               Field("systems", "Только ОС", "text", "AETHER, …")),
              run=_world("_letter"), check=lambda a: _need_item(a, "item", "msg", "письма"), refs=lambda a: [("item", a.get("item", ""), "grants")]))
register(Spec("forum", "Запись на форуме", WORLD, "Мир", "запись «{title}»",
              (Field("section", "Раздел", "section", "", True), Field("character", "От кого", "character", "система (SYS)"),
               Field("mode", "Режим", "select", "", False, (("new", "новая тема"), ("append", "дописать в тему"))),
               Field("title", "Заголовок", "text", "World log", True), Field("text", "Текст", "textarea", "{time}, {player}, {world_счётчик}", True)),
              run=_world("_forum"), check=_section_check))


# ---------- хозяин: переписка ----------

register(Spec("goto", "Перейти на шаг", HOST, "Переписка", "→ шаг {step}", (Field("step", "Шаг", "step", "", True), Field("delay", "Задержка, с", "number", "0"))))
register(Spec("bounce", "Вернуть как недоставленное", HOST, "Переписка", "вернуть письмо", ()))
