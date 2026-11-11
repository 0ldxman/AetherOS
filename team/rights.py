"""Права авторов в Студии: роль даёт уровень по разделам и отдельные опасные действия.

Автор это сотрудник (is_staff). Суперадмин (is_superuser) может всё и один управляет командой: ролями и авторами.
У автора без роли каждый раздел только на просмотр.

Запрос к API Студии относится к разделу по пути (rule_for). Чтение (GET и POST-предпросмотры) требует уровня «смотреть»,
остальное «править»; некоторые пути требуют ещё и действия (выброс игрока, удаление). Каждый путь API обязан найти своё
правило: это проверяет тест, чтобы новый эндпоинт не остался без прав.
"""
from dataclasses import dataclass

NONE, READ, EDIT = "none", "read", "edit"
LEVELS = (NONE, READ, EDIT)
LEVEL_LABELS = {NONE: "нет", READ: "смотреть", EDIT: "править"}

SECTIONS = {
    "disks": "Диски и файлы",
    "items": "Объекты",
    "machines": "Машины",
    "formats": "Форматы",
    "policies": "Политики входа",
    "systems": "Операционные системы",
    "scenes": "Сцены",
    "world": "Мир",
    "map": "Карта",
    "players": "Игроки",
    "mail": "Почта",
}

ACTIONS = {
    "delete": "Удалять",
    "players": "Выбрасывать и разблокировать игроков, привязывать учётки, выдавать токены",
    "keys": "Выдавать и забирать ключи игроков",
    "reset": "Сбрасывать прогресс игроков",
    "ban": "Отключать вход игрокам",
}

TEAM = "team"                  # раздел команды: смотреть могут все авторы, править только суперадмин
FREE = "free"                  # справочники и разборщики без данных мира: доступны любому автору

# последние части пути POST-запросов, которые ничего не меняют (предпросмотр, разбор, проверка, генерация)
SAFE_POST = {"preview", "parse", "format", "check", "outline", "build", "resolve", "generate", "randomart", "week", "try"}
# последние части пути, которым нужно действие с игроками
PLAYER_ACTIONS = {"kick", "unlock", "bind", "tokens"}


@dataclass(frozen=True)
class Rule:
    section: str
    level: str
    action: str = ""


def _section_of(parts):
    """Раздел по частям пути после /studio/api/."""
    head = parts[0] if parts else ""
    if head in ("", "me", "app-icons", "formats", "templates", "keys", "access", "layers", "dashboard", "comments", "boards", "tasks", "notifications"):
        return FREE
    if head in ("file-formats", "file-encodings"):
        return "formats"
    if head == "volumes":
        return "disks"
    if head in ("items", "wiki-volumes"):
        return "items"
    if head in ("machines", "policies", "systems", "world", "map", "scenes", "players", "mail", TEAM):
        return head
    return None


def rule_for(path, method):
    """Правило для запроса к API Студии (path без префикса /studio/api/) или None, если путь не знаком."""
    parts = [part for part in path.strip("/").split("/") if part]
    section = _section_of(parts)
    if section is None:
        return None
    method = method.upper()
    last = parts[-1] if parts else ""
    if method in ("GET", "HEAD", "OPTIONS") or (method == "POST" and last in SAFE_POST):
        return Rule(section, READ)
    action = ""
    if section == "machines" and (last in PLAYER_ACTIONS or (len(parts) >= 2 and parts[-2] == "tokens")):
        action = "players"
    elif section == "players":
        action = "keys" if "keys" in parts else {"kick": "players", "unlock": "players", "reset": "reset", "ban": "ban"}.get(last, "")
    elif method == "DELETE" and last != "lock" and section != FREE:           # снять свою метку, удалить своё сообщение
        action = "delete"
    return Rule(section, EDIT, action)


def level_of(user, section):
    if user.is_superuser or section == FREE:
        return EDIT
    if section == TEAM:
        return READ
    role = getattr(user, "role", None)
    if role is None:
        return READ
    return role.rights.get(section, NONE)


def can_act(user, action):
    if user.is_superuser:
        return True
    role = getattr(user, "role", None)
    return role is not None and action in role.actions


def refusal(user, rule):
    """Почему автору нельзя по правилу (текст для ответа 403) или пустая строка, если можно."""
    have = level_of(user, rule.section)
    if LEVELS.index(have) < LEVELS.index(rule.level):
        if rule.section == TEAM:
            return "Командой управляет только суперадмин."
        need = LEVEL_LABELS[rule.level]
        return f"Нет прав: раздел «{SECTIONS.get(rule.section, rule.section)}», нужно «{need}»."
    if rule.action and not can_act(user, rule.action):
        return f"Нет прав на действие: {ACTIONS[rule.action].lower()}."
    return ""


def summary(user):
    """Права автора для интерфейса: уровень каждого раздела и разрешённые действия."""
    return {
        "sections": {section: level_of(user, section) for section in SECTIONS},
        "actions": [action for action in ACTIONS if can_act(user, action)],
        "team": EDIT if user.is_superuser else READ,
    }
