"""Элементы рабочего стола, которые ОС включает и выключает независимо от стиля (SystemType.widgets, SystemType.widget_places).

Любой элемент можно включить в любой ОС. Если оболочка стиля рисует его сама (родной элемент), переключатель его показывает или
прячет. Если не рисует, стол вставляет общий элемент (desktop/elements/) в слот оболочки: «начало» или «конец» её главной панели,
док у края стола. Общий элемент рисуется на токенах стиля, а файл темы может дорисовать его по-своему ([data-theme] .el-…).

Поведение одно на всех (desktop/static/desktop/shell.js): меню запуска, поиск, задачи, док, столы и уведомления работают на любой
разметке с нужными data-shell. Выход из сессии всегда остаётся: меню, где он живёт, переключателем не прячется.
"""
from dataclasses import dataclass

PANEL_PLACES = {"start": "в начале панели", "end": "в конце панели"}
PANEL_END_FIRST = {"end": "в конце панели", "start": "в начале панели"}     # первым идёт место по умолчанию
DOCK_PLACES = {"bottom": "снизу", "left": "слева", "right": "справа"}


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    group: str
    hint: str
    native: tuple = ()           # оболочки, которые рисуют его сами
    hide: str = ""               # что прятать у родного элемента, когда выключен
    places: dict | None = None   # куда можно поставить добавленный (None: только вкл/выкл)
    locked: tuple = ()           # оболочки, где выключить нельзя: в нём выход из сессии


ALL = ("aether", "classic", "gnome", "modern", "phosphor", "tui", "workbench")

ITEMS = (
    Item("clock", "Часы", "Панель", "Время (игровое, в поясе машины).", ALL, "#clock"),
    Item("date", "Дата", "Панель", "Дата рядом с часами.", ALL, "#date"),
    Item("ping", "Пинг", "Панель", "Декоративный индикатор задержки связи.", ALL, ".ping"),
    Item("machine", "Имя машины", "Панель", "Логин и хост.", ("aether", "classic", "gnome", "phosphor", "tui"),
         "#machine-name, .fw-crumb, .fkeys-user, .fw-user", PANEL_PLACES),
    Item("notices", "Центр уведомлений", "Панель", "Журнал сообщений: кнопка со счётчиком и панель.",
         ("classic", "gnome", "modern", "phosphor", "tui", "workbench"),
         '[data-shell="notices-count"], [data-shell="notices-panel"], [data-shell="notices-toggle"]:not(#clock-plate)', PANEL_PLACES),
    Item("launcher", "Меню запуска", "Панель", "Кнопка со списком приложений.", ("classic", "gnome", "modern", "tui"),
         '.activities[data-shell="launcher"], .dock-grid[data-shell="launcher"], .fkeys [data-shell="launcher"]', PANEL_PLACES,
         locked=("classic", "modern")),
    Item("search", "Поиск приложений", "Панель", "Поле поиска: набор открывает меню запуска с найденным.", ("gnome", "modern", "tui"),
         '[data-shell="search"]', PANEL_END_FIRST),
    Item("tasks", "Панель задач", "Панель", "Открытые окна пунктами.", ("classic", "gnome", "modern", "tui"), '[data-shell="tasks"]', PANEL_END_FIRST),
    Item("workspaces", "Рабочие столы", "Панель", "Переключатель столов 1–4: окна живут на своём столе.", ("workbench",),
         '[data-shell="workspace"]', PANEL_END_FIRST),
    Item("console", "Кнопка консоли", "Панель", "Быстро открыть и свернуть терминал.", ("phosphor",), '[data-shell="console-toggle"]', PANEL_END_FIRST),
    Item("dock", "Док", "Стол", "Полоса приложений у края стола, запущенные отмечены.", ("gnome", "workbench"), "#dock, .fp-apps", DOCK_PLACES),
    Item("icons", "Значки на столе", "Стол", "Значки приложений и файлов на самом столе.", ALL, "#icons"),
    Item("ticker", "Бегущая строка событий", "Стол", "Жёлтая строка моментов мира у верхнего края стола.", ALL, ".moment-bar"),
    Item("toasts", "Всплывающие уведомления", "Стол", "Новости, почта, события. Выключено: в центр уведомлений они всё равно попадают.", ALL, "#toasts"),
)
BY_KEY = {item.key: item for item in ITEMS}

# у этих оболочек главная панель снизу: всплывающие панели открываются вверх от неё, док поднимается выше неё
BOTTOM_PANEL = {"modern", "workbench"}


def shell_of(style):
    from machines.world import styles

    found = styles.STYLES.get(style)
    return style if found is not None and found.shell else styles.DEFAULT_STYLE


def is_native(key, style):
    return shell_of(style) in BY_KEY[key].native


def clean(data):
    """Только известные ключи со значением true/false; нет ключа — «как в стиле»."""
    return {key: bool(value) for key, value in (data or {}).items() if key in BY_KEY and isinstance(value, bool)}


def clean_places(data):
    out = {}
    for key, value in (data or {}).items():
        item = BY_KEY.get(key)
        if item is not None and item.places and value in item.places:
            out[key] = value
    return out


def is_locked(key, style):
    return shell_of(style) in BY_KEY[key].locked


def resolve(style, data):
    """{ключ: включён}: «как в стиле» — включено, если элемент родной для оболочки, иначе выключено. Запертое всегда включено."""
    chosen = clean(data)
    return {item.key: True if is_locked(item.key, style) else chosen.get(item.key, is_native(item.key, style)) for item in ITEMS}


def place_of(key, places):
    item = BY_KEY[key]
    if not item.places:
        return ""
    return (places or {}).get(key) or next(iter(item.places))


def added(style, data, places):
    """Включённые элементы, которых нет в оболочке стиля: их вставляет стол. {ключ: место}."""
    state = resolve(style, data)
    return {key: place_of(key, places) for key, on in state.items() if on and not is_native(key, style) and BY_KEY[key].places}


def hidden_css(style, data):
    """CSS, который прячет выключенные родные элементы оболочки."""
    state = resolve(style, data)
    off = [BY_KEY[key].hide for key, on in state.items() if not on and is_native(key, style) and BY_KEY[key].hide]
    return "".join(f"{selector}{{display:none!important}}" for selector in off)


def warnings(style, data):
    """Предупреждения для Студии: например, приложения открыть нечем."""
    state = resolve(style, data)
    if shell_of(style) == "phosphor":           # главное меню прошивки всегда показывает приложения
        return []
    if not any(state[key] for key in ("icons", "launcher", "dock")):
        return ["Выключены и значки, и меню запуска, и док: приложения на этой ОС открыть нечем, кроме ссылок и хуков."]
    return []


NATIVE_LAUNCHER_PANEL = {"classic", "gnome", "modern", "tui"}       # где своя панель меню запуска (в неё и ищет поиск)
NATIVE_NOTICES_PANEL = {"classic", "gnome", "modern", "phosphor", "tui", "workbench"}


def slot_context(style, data, places, slot):
    """Что вставить в слот оболочки: start | end — на главную панель, desk — док и всплывающие панели. Для desktop/elements/slot.html."""
    found = added(style, data, places)
    shell = shell_of(style)
    context = {"edge": "bottom" if shell in BOTTOM_PANEL else "top", "slot": slot}
    if slot == "desk":
        return {**context, "dock": found.get("dock", ""),
                "launcher_panel": ("launcher" in found or "search" in found) and shell not in NATIVE_LAUNCHER_PANEL,
                "notices_panel": "notices" in found and shell not in NATIVE_NOTICES_PANEL}
    return {**context, "els": [key for key, place in found.items() if place == slot and key != "dock"]}
