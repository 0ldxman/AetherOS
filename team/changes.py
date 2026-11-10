"""Лента изменений Студии и проверка версии при сохранении: одна система на все редакторы.

Каждый успешный запрос Студии, который что-то меняет, оставляет запись Change (кто, когда, что, действие). Номер последней
записи это «состояние мира»: ответ на чтение несёт его (заголовок X-Version), фронт запоминает номер для загруженного адреса
и при сохранении шлёт его обратно (X-Base-Version). Если после загрузки кто-то записал изменение в тот же адрес или под ним,
сохранение отвечает 409 с тем, кто и когда; X-Force: 1 сохраняет поверх.

Ключ сущности это путь запроса без префикса API (machines/3/accounts/4): изменение под путём (machines/3/groups/x/disable)
тоже считается изменением сущности machines/3/groups/x. Объекты и файлы без объекта проверяют версию сами, подробнее
(OWN_CHECK), но в ленту пишутся так же.
"""
import json
import re

from django.core import serializers
from django.db.models import Max, Q

from team import rights
from team.models import Change

# пути, которые не пишутся в ленту: пульс мягкой блокировки объекта
QUIET = re.compile(r"^(items/\d+/lock|comments(/.*)?|boards(/.*)?)$")              # и обсуждения: у них своя лента на Главной
# пути со своей, более подробной проверкой версии (тело запроса version)
OWN_CHECK = re.compile(r"^(items/\d+(/.*)?|volumes/\d+/text-files/\d+(/.*)?)$")

ACTION_LABELS = {"create": "создание", "update": "изменение", "delete": "удаление", "act": "действие"}

# слова хвоста пути для сводки
TAIL_WORDS = {
    "accounts": "учётка", "groups": "группа", "mounts": "монтирование", "exports": "экспорт", "files": "файлы",
    "kick": "выброс игрока", "unlock": "разблокировка", "bind": "привязка учётки", "tokens": "токен", "content": "содержимое",
    "protection": "защита", "placements": "размещение", "revisions": "версия", "restore": "восстановление", "keys": "ключи",
    "detach": "отвязка", "to-text": "в текст", "to-item": "в объект", "places": "места", "image": "образ", "blackouts": "отключения",
    "scenes": "сцены", "style": "стиль", "move": "перенос", "copy": "копия", "rename": "переименование", "delete": "удаление",
    "folder": "папка", "file": "файл", "folders": "папка", "links": "ссылка", "rights": "права", "reset": "сброс", "open": "своя копия",
    "labels": "подпись", "disable": "отключение", "territory": "территории", "apply": "покраска", "erase": "ластик",
    "transfer": "передача", "roles": "роль", "authors": "автор", "import": "загрузка", "text-files": "файл",
    "take": "забран", "ban": "вход", 
}


def _label(model_path, field, pk, lookup="pk"):
    from django.apps import apps

    model = apps.get_model(model_path)
    obj = model.objects.filter(**{lookup: pk}).first()
    if obj is None:
        return str(pk), None
    value = obj
    for part in field.split("."):
        value = getattr(value, part, "") if value is not None else ""
    return str(value or pk), obj


# (шаблон пути сущности, вид, модель, поле подписи, поиск, ссылка в Студии); первое совпадение
ENTITIES = [
    (r"^machines/(\d+)/accounts/(\d+)", "Учётка", "machines.MachineProfile", "login", "pk", "#/machines/{0}/accounts/{1}"),
    (r"^machines/(\d+)", "Машина", "machines.Machine", "hostname", "pk", "#/machines/{0}"),
    (r"^items/(\d+)", "Объект", "filesystem.Item", "name", "pk", "#/items/{0}"),
    (r"^volumes/(\d+)/text-files/(\d+)", "Файл", "filesystem.Placement", "name", "pk", "#/volumes/{0}/text/{1}"),
    (r"^volumes/(\d+)", "Диск", "filesystem.Volume", "slug", "pk", "#/volumes/{0}"),
    (r"^policies/(\d+)", "Политика входа", "machines.EntryPolicy", "name", "pk", "#/policies/{0}"),
    (r"^systems/([^/]+)", "ОС", "machines.SystemType", "code", "code", "#/systems/{0}"),
    (r"^scenes/([^/]+)", "Сцена", "machines.SceneScript", "slug", "slug", "#/scenes/{0}"),
    (r"^file-formats/([^/]+)", "Формат", "filesystem.FileFormat", "name", "name", "#/formats/{0}"),
    (r"^file-encodings/([^/]+)", "Кодировка", "filesystem.FileEncoding", "name", "name", "#/encodings/{0}"),
    (r"^map/scenes/(\d+)", "Сцена карты", "map.MapScene", "title", "pk", "#/map/scenes/{0}"),
    (r"^map/countries/(\d+)", "Страна", "map.Country", "name", "pk", "#/map/countries/{0}"),
    (r"^map/provinces/(\d+)", "Провинция", "map.Province", "name", "pk", "#/map/provinces/{0}"),
    (r"^map/labels/(\d+)", "Подпись карты", "map.CountryLabel", "text", "pk", "#/map/labels"),
    (r"^map/ownerships/(\d+)", "Владение", "map.Ownership", "pk", "pk", "#/map/ownerships"),
    (r"^players/(\d+)", "Игрок", "users.User", "username", "pk", "#/players/{0}"),
    (r"^team/roles/(\d+)", "Роль", "team.Role", "name", "pk", "#/team/roles/{0}"),
    (r"^team/authors/(\d+)", "Автор", "users.User", "username", "pk", "#/team"),
]
# сущности без своего номера: весь раздел целиком
SINGLES = [
    (r"^world", "Мир", "настройки мира", "#/world"),
    (r"^map/territory", "Территории", "территории карты", "#/map/territory"),
    (r"^map/scenes", "Сцена карты", "сцены карты", "#/map/scenes"),
]
# коллекции, в которые создают: ответ называет новый номер или имя
COLLECTIONS = {
    "machines": "id", "items": "id", "volumes": "id", "policies": "id", "systems": "code", "scenes": "slug",
    "file-formats": "name", "file-encodings": "name", "map/scenes": "id", "map/countries": "id", "map/provinces": "id",
    "team/roles": "id",
}


def describe(path, created=None):
    """(вид, подпись, ссылка, объект модели или None, хвост пути после сущности) для пути API.

    created: ответ на создание (словарь), из него берётся номер новой сущности."""
    if created and path in COLLECTIONS:
        value = created.get(COLLECTIONS[path])
        if value is not None:
            path = f"{path}/{value}"
    for pattern, kind, model, field, lookup, link in ENTITIES:
        found = re.match(pattern, path)
        if found:
            ids = found.groups()
            label, obj = _label(model, field, ids[-1], lookup)
            if kind == "Учётка" and obj is not None:
                label = f"{obj.login}@{obj.machine.hostname}"
            return kind, label, link.format(*ids), obj, path[found.end():].strip("/")
    for pattern, kind, label, link in SINGLES:
        found = re.match(pattern, path)
        if found:
            return kind, label, link, None, path[found.end():].strip("/")
    head = path.split("/")[0]
    return head, path, "", None, ""


def _summary(tail):
    words = [TAIL_WORDS[part] for part in tail.split("/") if part in TAIL_WORDS]
    return ": ".join(dict.fromkeys(words))


def _action(method, path):
    if method == "DELETE":
        return "delete"
    if method == "POST" and path in COLLECTIONS:
        return "create"
    if method in ("PUT", "PATCH"):
        return "update"
    return "act"


def current():
    """Номер последней записи ленты (0, если лента пуста)."""
    return Change.objects.aggregate(top=Max("pk"))["top"] or 0


def newer(path, base):
    """Запись, сделанная по пути (или под ним) после номера base, или None."""
    found = Change.objects.filter(Q(path=path) | Q(path__startswith=path + "/"), pk__gt=base)
    return found.select_related("user").order_by("-pk").first()


def records(path, method):
    """Пишется ли запрос в ленту: меняющий (по правилам прав), не пульс блокировки."""
    rule = rights.rule_for(path, method)
    return rule is not None and rule.level == rights.EDIT and not QUIET.match(path)


def checks(path, method):
    """Проверяется ли версия: правка или удаление сущности, у которой нет своей проверки."""
    return method in ("PUT", "PATCH", "DELETE") and records(path, method) and not OWN_CHECK.match(path)


def snapshot(path):
    """Снимок сущности перед удалением (JSON сериализатора Django) или None."""
    _, _, _, obj, tail = describe(path)
    if obj is None or tail or obj._meta.label == "users.User":          # автора не удаляют, а убирают из команды
        return None
    return json.loads(serializers.serialize("json", [obj]))[0]


def record(user, method, path, created=None, snap=None, described=None):
    kind, label, link, _, tail = described or describe(path, created)
    rule = rights.rule_for(path, method)
    action = _action(method, path)
    if created and path in COLLECTIONS and COLLECTIONS[path] in created:
        path = f"{path}/{created[COLLECTIONS[path]]}"
    return Change.objects.create(
        user=user, username=user.get_username(), method=method, path=path[:512],
        section=rule.section if rule else "", action=action,
        kind=kind, label=label[:200], link=link, summary=_summary(tail), snapshot=snap,
    )


def feed(author=None, section="", before=None, limit=50):
    rows = Change.objects.select_related("user").order_by("-pk")
    if author:
        rows = rows.filter(user_id=author)
    if section:
        rows = rows.filter(section=section)
    if before:
        rows = rows.filter(pk__lt=before)
    return list(rows[:limit])


def conflict_text(change):
    at = change.at.astimezone().strftime("%d.%m %H:%M")
    what = f", {change.summary}" if change.summary else ""
    return f"Пока вы правили, это уже изменили ({change.username}, {at}{what})."
