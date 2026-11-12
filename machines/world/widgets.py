"""Элементы оболочки рабочего стола, которые ОС может включать и выключать (SystemType.widgets).

Вид у элемента свой в каждом стиле: переключатель только показывает или прячет то, что оболочка стиля уже рисует.
Какие элементы есть у оболочки, задано в SUPPORT; чего у оболочки нет, того переключатель в Студии не предлагает.
Выход из сессии (disconnect) живёт в меню подключения или запуска: такое меню выключить нельзя, оно в SUPPORT не входит.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    group: str
    hint: str
    hide: str = ""          # CSS-селекторы того, что прятать, когда выключено


ITEMS = (
    Item("clock", "Часы", "Панель", "Время на панели (игровое, в поясе машины).", "#clock"),
    Item("date", "Дата", "Панель", "Дата рядом с часами.", "#date"),
    Item("ping", "Пинг", "Панель", "Декоративный индикатор задержки связи.", ".ping"),
    Item("machine", "Имя машины", "Панель", "Логин и хост на панели.", "#machine-name, .fw-crumb"),
    Item("notices", "Центр уведомлений", "Панель", "Журнал сообщений: кнопка и счётчик. Сами всплывающие уведомления — отдельно.",
         '[data-shell="notices-count"], [data-shell="notices-panel"], [data-shell="notices-toggle"]:not(#clock-plate)'),
    Item("launcher", "Меню запуска", "Панель", "Кнопка списка приложений.", '[data-shell="launcher"], [data-shell="launcher-panel"]'),
    Item("search", "Поиск приложений", "Панель", "Поле поиска в меню запуска.", '[data-shell="search"]'),
    Item("tasks", "Панель задач", "Панель", "Открытые окна пунктами на панели.", '[data-shell="tasks"]'),
    Item("dock", "Док", "Панель", "Полоса закреплённых приложений.", "#dock"),
    Item("workspaces", "Рабочие столы", "Панель", "Переключатель столов 1–4.", '[data-shell="workspace"]'),
    Item("console", "Кнопка консоли", "Панель", "Быстрый вызов терминала.", '[data-shell="console-toggle"]'),
    Item("icons", "Значки на столе", "Стол", "Значки приложений и файлов на самом столе.", "#icons"),
    Item("ticker", "Бегущая строка событий", "Стол", "Жёлтая строка моментов мира у верхнего края стола.", ".moment-bar"),
    Item("toasts", "Всплывающие уведомления", "Стол", "Новости, почта, события. Выключено: в центр уведомлений они всё равно попадают.", "#toasts"),
)
BY_KEY = {item.key: item for item in ITEMS}

_DESK = ("icons", "ticker", "toasts")
SUPPORT = {                 # оболочка -> что в ней есть (всё по умолчанию включено, как и было)
    "aether": ("clock", "date", "ping", "machine") + _DESK,
    "classic": ("clock", "date", "ping", "machine", "notices", "tasks") + _DESK,
    "gnome": ("clock", "date", "ping", "machine", "notices", "launcher", "search", "tasks", "dock") + _DESK,
    "modern": ("clock", "date", "ping", "notices", "search", "tasks") + _DESK,
    "phosphor": ("clock", "date", "ping", "machine", "notices", "console") + _DESK,
    "tui": ("clock", "date", "ping", "notices", "launcher", "search", "tasks") + _DESK,
    "workbench": ("clock", "date", "ping", "notices", "workspaces") + _DESK,
}


def shell_of(style):
    from machines.world import styles

    found = styles.STYLES.get(style)
    return style if found is not None and found.shell else styles.DEFAULT_STYLE


def supported(style):
    return SUPPORT.get(shell_of(style), SUPPORT["aether"])


def clean(data):
    """Только известные ключи со значением true/false; отсутствие ключа — «как в стиле»."""
    return {key: bool(value) for key, value in (data or {}).items() if key in BY_KEY and isinstance(value, bool)}


def resolve(style, data):
    """{ключ: включён} для оболочки стиля: «как в стиле» — включено; чего в оболочке нет — нет в ответе."""
    chosen = clean(data)
    return {key: chosen.get(key, True) for key in supported(style)}


def hidden_css(style, data):
    """CSS, который прячет выключенные элементы этой ОС."""
    off = [BY_KEY[key].hide for key, on in resolve(style, data).items() if not on and BY_KEY[key].hide]
    return "".join(f"{selector}{{display:none!important}}" for selector in off)


def warnings(style, data):
    """Предупреждения для Студии: например, приложения открыть нечем."""
    state = resolve(style, data)
    ways = [key for key in ("icons", "launcher", "dock") if key in state]
    if ways and not any(state[key] for key in ways):
        return ["Выключены и значки, и меню запуска: приложения на этой ОС открыть нечем, кроме ссылок и хуков."]
    return []
