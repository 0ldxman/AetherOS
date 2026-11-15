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
    from engine import values

    name = (action.get("name") or "").strip()
    if not name:
        raise ActionError("метка без имени")
    values.set_tag(values.PLAYER, ctx.user.pk, name, True, source=ctx.source, actor=ctx.user, _depth=ctx.depth)


def _unflag(action, ctx):
    from engine import values

    name = (action.get("name") or "").strip()
    if name:
        values.set_tag(values.PLAYER, ctx.user.pk, name, False, source=ctx.source, actor=ctx.user, _depth=ctx.depth)


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
    from filesystem import arrivals

    arrivals.got(ctx.box.view, path, item, "scenario")


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


# ---------- экран игрока: эффекты уходят в очередь (engine/push.py), стол забирает их опросом ----------

SCREEN = "Экран игрока"


def _push(op, build):
    def go(action, ctx):
        from engine import push

        push.send(ctx.user, op, **build(action))
    return go


def scene_steps(slug):
    """Сцена из Студии (machines.SceneScript), собранная для проигрывателя."""
    from machines.models.scenes import SceneScript, resolve_script
    from machines.world.dates import world
    from scenes.script import compile_script

    script = SceneScript.objects.filter(slug=slug or "").first()
    if script is None:
        raise ActionError(f"нет сцены «{slug or '?'}»")
    scene, errors = compile_script(script.body, {}, world().game_now, resolve_script)
    if errors:
        raise ActionError(f"сцена «{slug}»: {errors[0]}")
    return scene.to_dict()


def _scene_check(action):
    from machines.models.scenes import SceneScript

    return [] if SceneScript.objects.filter(slug=action.get("scene") or "").exists() else [f"нет сцены «{action.get('scene') or '?'}»"]


def _int(value, default, low=0, high=None):
    try:
        number = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        number = default
    number = max(low, number)
    return min(number, high) if high is not None else number


register(Spec("notify", "Уведомление", USER, SCREEN, "уведомление «{title}»",
              (Field("title", "Заголовок", "text", "INCOMING", True), Field("text", "Текст", "textarea")),
              run=_push("notify", lambda a: {"title": a.get("title", ""), "text": a.get("text", "")})))
register(Spec("ticker", "Бегущая строка", USER, SCREEN, "строка «{text}»",
              (Field("text", "Текст", "text", "", True), Field("seconds", "Сколько держать, с", "number", "30")),
              run=_push("ticker", lambda a: {"text": a.get("text", ""), "seconds": _int(a.get("seconds"), 30, 3, 3600)})))
register(Spec("windows", "Окна ошибок", USER, SCREEN, "окна «{message}»",
              (Field("message", "Сообщение", "text", "unreachable", True), Field("count", "Сколько окон", "number", "6"),
               Field("gap", "Пауза, мс", "number", "500")),
              run=_push("alert", lambda a: {"message": a.get("message", ""), "count": _int(a.get("count"), 6, 1, 40), "gap": _int(a.get("gap"), 500, 0, 10000)})))
register(Spec("open_window", "Открыть окно", USER, SCREEN, "открыть {url}",
              (Field("url", "Адрес", "text", "apps/wiki/go/secret/", True), Field("title", "Заголовок окна", "text")),
              run=_push("open", lambda a: {"url": a.get("url", ""), "title": a.get("title", "") or a.get("url", ""), "id": "graph-" + str(abs(hash(a.get("url", ""))) % 10**8)})))
register(Spec("blackout", "Чёрный экран", USER, SCREEN, "чёрный экран «{title}»",
              (Field("title", "Заголовок", "text", "kernel panic"), Field("text", "Текст", "textarea", "", True),
               Field("tone", "Тон", "select", "", False, (("error", "ошибка"), ("info", "сообщение"))), Field("hold", "Держать после текста, мс", "number", "2600")),
              run=_push("blackout", lambda a: {"title": a.get("title", ""), "text": a.get("text", ""), "tone": a.get("tone") or "error", "delay": 400,
                                               "hold": _int(a.get("hold"), 2600, 0, 60000)})))
register(Spec("terminal_text", "Текст в терминале", USER, SCREEN, "в терминал «{text}»", (Field("text", "Текст", "textarea", "broadcast from root: …", True),),
              run=_push("terminal", lambda a: {"text": a.get("text", "")})))


def _scene_push(op):
    def go(action, ctx):
        from engine import push

        push.send(ctx.user, op, scene=scene_steps(action.get("scene")))
    return go


register(Spec("terminal_scene", "Сцена в терминале", USER, SCREEN, "сцена {scene} в терминале", (Field("scene", "Сцена", "scene", "", True),),
              run=_scene_push("tscene"), check=_scene_check))
register(Spec("scene", "Сцена на весь экран", USER, SCREEN, "сцена {scene}", (Field("scene", "Сцена", "scene", "", True),),
              run=_scene_push("scene"), check=_scene_check))


# ---------- игрок: счётчик ----------

def _player_count(action, ctx):
    from engine import values

    name = (action.get("name") or "").strip()
    if not name:
        raise ActionError("счётчик без имени")
    if action.get("mode") == "set":
        values.put(values.PLAYER, ctx.user.pk, name, _int(action.get("value"), 0, -10**9), source=ctx.source, actor=ctx.user, _depth=ctx.depth)
    else:
        values.add(values.PLAYER, ctx.user.pk, name, _int(action.get("delta"), 1, -10**9), source=ctx.source, actor=ctx.user, _depth=ctx.depth)


register(Spec("player_count", "Счётчик игрока", USER, "Игрок", "count:{name} {mode} {delta}{value}",
              (Field("name", "Счётчик", "text", "hints", True), Field("mode", "Как", "select", "", False, (("add", "прибавить"), ("set", "задать"))),
               Field("delta", "Сколько прибавить", "number", "1"), Field("value", "Задать значение", "number")),
              run=_player_count))


# ---------- файлы игрока ----------

def _path(action, ctx, name="path"):
    from mail import letters

    path = letters.fill(action.get(name, ""), {"login": ctx.box.login})
    if not path.startswith("/"):
        raise ActionError("путь должен начинаться с «/»")
    return path


def _file_delete(action, ctx):
    path = _path(action, ctx)
    if not ctx.box.view.exists(path):
        raise ActionError(f"нет файла {path}")
    ctx.box.view.remove(path)


def _layer_remove(action, ctx):
    from filesystem.layers.unlock import unlock_file

    view, path = ctx.box.view, _path(action, ctx)
    if not view.exists(path):
        raise ActionError(f"нет файла {path}")
    outcome = unlock_file(view, path, None, force=True)
    if not outcome.result.removed:
        raise ActionError(f"у {path} нет слоёв")


def _file_change(action, ctx):
    view, path = ctx.box.view, _path(action, ctx)
    if not view.exists(path):
        raise ActionError(f"нет файла {path}")
    mode = action.get("mode") or "replace"
    if mode == "replace":
        item = _item(action.get("item"))
        if item is None:
            raise ActionError(f"нет объекта «{action.get('item')}»")
        view.remove(path)
        view.put_item(path, item)
    elif mode == "move":
        from filesystem import fileevents

        fileevents.move(view, path, _path(action, ctx, "target"))
    elif mode == "reset":
        view.set_progress(path, "")
    else:
        raise ActionError(f"неизвестный режим «{mode}»")


register(Spec("file_delete", "Удалить файл", ACCOUNT, "Игрок", "удалить {path}", (Field("path", "Путь", "path", "/home/{login}/report.txt", True),),
              run=_file_delete, check=lambda a: [] if (a.get("path") or "").startswith("/") else ["путь должен начинаться с «/»"]))
register(Spec("file_change", "Изменить файл", ACCOUNT, "Игрок", "{mode} {path}",
              (Field("path", "Путь", "path", "/home/{login}/report.txt", True),
               Field("mode", "Что сделать", "select", "", False, (("replace", "подменить объект"), ("move", "переименовать / переместить"), ("reset", "вернуть слои"))),
               Field("item", "Новый объект", "object"), Field("target", "Новый путь", "path", "/home/{login}/old/report.txt")),
              run=_file_change,
              check=lambda a: (["путь должен начинаться с «/»"] if not (a.get("path") or "").startswith("/") else [])
              + (_need_item(a, "item") if (a.get("mode") or "replace") == "replace" else [])
              + (["нужен новый путь"] if a.get("mode") == "move" and not (a.get("target") or "").startswith("/") else []),
              refs=lambda a: [("item", a.get("item", ""), "grants")] if a.get("item") else []))


# ---------- мир: машины, учётки, сеть, моменты, персонажи ----------

def _machine_of(action):
    from machines.models import Machine

    machine = Machine.objects.filter(hostname=action.get("host") or "").first()
    if machine is None:
        raise ActionError(f"нет машины «{action.get('host') or '?'}»")
    return machine


def _machine_power(action, ctx):
    from machines.world import power

    power.set_state(_machine_of(action), action.get("state") or "stop", _int(action.get("minutes"), 5, 1, 7 * 24 * 60), ctx.source)


def _account(action, ctx):
    from datetime import timedelta

    from django.utils import timezone

    from machines.models import AccountBlock, MachineProfile

    machine = _machine_of(action)
    profile = MachineProfile.objects.filter(machine=machine, login=action.get("login") or "").first()
    if profile is None:
        raise ActionError(f"нет учётки {action.get('login')}@{machine.hostname}")
    everyone = action.get("scope") == "all"
    if not everyone and ctx.user is None:
        raise ActionError("«этому игроку» без игрока")
    user = None if everyone else ctx.user
    if action.get("password"):
        if not everyone:
            raise ActionError("пароль меняется только для всех")
        from django.contrib.auth.hashers import make_password

        profile.password_hash = make_password(str(action["password"]))
        profile.save(update_fields=["password_hash"])
    if action.get("unblock"):
        AccountBlock.objects.filter(profile=profile, user=user).delete()
    minutes = _int(action.get("block"), 0, 0, 30 * 24 * 60)
    if minutes:
        AccountBlock.objects.create(profile=profile, user=user, until=timezone.now() + timedelta(minutes=minutes), text=action.get("text", "")[:255])


def _net(action, ctx):
    from machines.models import NetNode, NetResource
    from machines.models.net import normalize_address

    resource = NetResource.objects.filter(address=normalize_address(action.get("address", ""))).first()
    if resource is None:
        raise ActionError(f"нет сервера «{action.get('address') or '?'}»")
    path = "/".join(part for part in (action.get("path") or "").split("/") if part)
    if action.get("path") is not None and path:
        node = NetNode.objects.filter(resource=resource, path=path).first()
        if node is None:
            raise ActionError(f"нет узла {resource.address}/{path}")
        target = node
    else:
        target = resource
    fields = []
    if action.get("token") is not None and action.get("token") != "":
        target.token = "" if action["token"] == "-" else str(action["token"])
        fields.append("token")
    if isinstance(target, NetNode) and action.get("response"):
        target.response = action["response"]
        fields.append("response")
    if fields:
        target.save(update_fields=fields)


def _moment(start):
    def go(action, ctx):
        from world import moments
        from world.models import WorldMoment

        moment = WorldMoment.objects.filter(name=action.get("moment") or "").first()
        if moment is None:
            raise ActionError(f"нет момента «{action.get('moment') or '?'}»")
        (moments.start_now if start else moments.stop_now)(moment, ctx.source)
    return go


def _character_tag(action, ctx):
    from characters.models import Character

    character = Character.objects.filter(code=str(action.get("character") or "").upper()).first()
    if character is None:
        raise ActionError(f"нет персонажа {action.get('character') or '?'}")
    tag = (action.get("tag") or "").strip().lower()
    if not tag:
        raise ActionError("тег без имени")
    from engine import values

    values.set_tag("character", character.pk, tag, (action.get("mode") or "add") == "add", source=ctx.source, actor=ctx.user, _depth=ctx.depth)


OWNER_FIELDS = (
    Field("owner", "Владелец", "select", "", False, (("world", "мир"), ("player", "игрок"), ("character", "персонаж"), ("machine", "машина"),
                                                     ("server", "сервер"), ("object", "объект"))),
    Field("who", "Игрок", "player", "игрок хода"), Field("character", "Персонаж", "character"), Field("machine", "Машина", "machine"),
    Field("server", "Сервер", "server"), Field("item", "Объект", "object"),
    Field("scope", "Чьё", "select", "", False, (("shared", "общее"), ("player", "для игрока"))),
    Field("for", "Для игрока", "player", "игрок хода"),
)


def _tag(action, ctx):
    from engine import values

    owner, oid, user = values.target(action, ctx.user)
    values.set_tag(owner, oid, action.get("name") or "", (action.get("mode") or "on") == "on", user=user, source=ctx.source, actor=ctx.user,
                   _depth=ctx.depth)


def _count(action, ctx):
    from engine import values

    owner, oid, user = values.target(action, ctx.user)
    if action.get("mode") == "set":
        values.put(owner, oid, action.get("name") or "", _int(action.get("value"), 0, -10**9), user=user, source=ctx.source, actor=ctx.user,
                   _depth=ctx.depth)
    else:
        values.add(owner, oid, action.get("name") or "", _int(action.get("delta"), 1, -10**9), user=user, source=ctx.source, actor=ctx.user,
                   _depth=ctx.depth)


register(Spec("tag", "Тег", WORLD, "Теги и счётчики", "{mode} тег {owner} {name}",
              (Field("mode", "Что сделать", "select", "", False, (("on", "поставить"), ("off", "снять"))), *OWNER_FIELDS,
               Field("name", "Тег", "text", "", True)), run=_tag))
register(Spec("count", "Счётчик", WORLD, "Теги и счётчики", "{mode} счётчик {owner} {name} {delta}{value}",
              (Field("mode", "Что сделать", "select", "", False, (("add", "прибавить"), ("set", "задать"))), *OWNER_FIELDS,
               Field("name", "Счётчик", "text", "", True), Field("delta", "Сколько прибавить", "number", "1"), Field("value", "Задать значение", "number")),
              run=_count))


register(Spec("layer_remove", "Снять верхний слой", ACCOUNT, "Игрок", "снять слой {path}", (Field("path", "Путь", "path", "", True),),
              run=_layer_remove))


register(Spec("machine_power", "Изменить машину", WORLD, "Машины", "{host}: {state}",
              (Field("host", "Машина", "machine", "", True),
               Field("state", "Что сделать", "select", "", False, (("stop", "остановить"), ("start", "запустить"), ("reboot", "перезагрузить"))),
               Field("minutes", "Перезагрузка, мин", "number", "5")),
              run=_machine_power))
register(Spec("account", "Изменить учётку", WORLD, "Машины", "{login}@{host}",
              (Field("host", "Машина", "machine", "", True), Field("login", "Учётка", "text", "admin", True),
               Field("scope", "Для кого", "select", "", False, (("player", "этому игроку"), ("all", "всем"))),
               Field("block", "Заблокировать, мин", "number", "0 — не блокировать"), Field("text", "Текст блокировки", "text"),
               Field("unblock", "Снять блокировку", "bool"), Field("password", "Новый пароль (для всех)", "text")),
              run=_account))
register(Spec("net_node", "Изменить узел сети", WORLD, "Машины", "{address}/{path}",
              (Field("address", "Сервер", "text", "apollo.com", True), Field("path", "Узел (пусто — сервер)", "text", "info/data"),
               Field("token", "Новый токен (- убрать)", "text"), Field("response", "Новый ответ страницы", "textarea")),
              run=_net))
register(Spec("moment_start", "Начать момент", WORLD, "Мир", "начать {moment}", (Field("moment", "Момент", "moment", "", True),), run=_moment(True)))
register(Spec("moment_end", "Закончить момент", WORLD, "Мир", "закончить {moment}", (Field("moment", "Момент", "moment", "", True),), run=_moment(False)))
register(Spec("character_tag", "Тег персонажа", WORLD, "Мир", "{character}: {tag}",
              (Field("character", "Персонаж", "character", "", True), Field("tag", "Тег", "text", "exposed", True),
               Field("mode", "Что сделать", "select", "", False, (("add", "поставить"), ("remove", "снять")))),
              run=_character_tag))


# ---------- хозяин: переписка ----------

register(Spec("goto", "Перейти на шаг", HOST, "Переписка", "→ шаг {step}", (Field("step", "Шаг", "step", "", True), Field("delay", "Задержка, с", "number", "0"))))
register(Spec("bounce", "Вернуть как недоставленное", HOST, "Переписка", "вернуть письмо", ()))
