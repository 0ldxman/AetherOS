"""Элементы самого стола, которые ОС включает и выключает независимо от стиля (SystemType.widgets, SystemType.widget_places).

Панель с её элементами раскладывается отдельно (machines/world/panel.py). Здесь то, что лежит на столе: док, значки, бегущая
строка, всплывающие уведомления, и дата у часов. Если стиль рисует элемент сам (родной), переключатель его показывает или прячет;
если не рисует, стол вставляет общий элемент (док из desktop/elements/desk.html).
"""
from dataclasses import dataclass

DOCK_PLACES = {"bottom": "снизу", "left": "слева", "right": "справа"}


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    group: str
    hint: str
    native: tuple = ()           # стили, которые рисуют его сами
    hide: str = ""               # что прятать у родного элемента, когда выключен
    places: dict | None = None   # куда можно поставить добавленный (None: только вкл/выкл)


ALL = ("aether", "classic", "gnome", "modern", "phosphor", "tui", "workbench")

ITEMS = (
    Item("date", "Дата у часов", "Панель", "Дата под или рядом с часами.", ALL, "#date"),
    Item("dock", "Док", "Стол", "Полоса приложений у края стола, запущенные отмечены.", ("gnome",), "#dock, .dock-wrap", DOCK_PLACES),
    Item("icons", "Значки на столе", "Стол", "Значки приложений и файлов на самом столе.", ALL, "#icons"),
    Item("ticker", "Бегущая строка событий", "Стол", "Жёлтая строка моментов мира у верхнего края стола.", ALL, ".moment-bar"),
    Item("toasts", "Всплывающие уведомления", "Стол", "Новости, почта, события. Выключено: в журнал сообщений они всё равно попадают.", ALL, "#toasts"),
)
BY_KEY = {item.key: item for item in ITEMS}


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


def resolve(style, data):
    """{ключ: включён}: «как в стиле» — включено, если элемент родной для стиля, иначе выключено."""
    chosen = clean(data)
    return {item.key: chosen.get(item.key, is_native(item.key, style)) for item in ITEMS}


def dock_place(style, data, places):
    """Где стол добавляет свой док ("" — не добавляет: выключен или стиль рисует его сам)."""
    if not resolve(style, data)["dock"] or is_native("dock", style):
        return ""
    return (places or {}).get("dock") or next(iter(DOCK_PLACES))


def hidden_css(style, data):
    """CSS, который прячет выключенные родные элементы стиля."""
    state = resolve(style, data)
    off = [BY_KEY[key].hide for key, on in state.items() if not on and is_native(key, style) and BY_KEY[key].hide]
    return "".join(f"{selector}{{display:none!important}}" for selector in off)


def warnings(style, data, panel_data=None):
    """Предупреждения для Студии: например, приложения открыть нечем."""
    from machines.world import panel

    look = panel.of(style, panel_data)["look"]
    if look in ("phosphor", "tui"):                 # главное меню прошивки и список приложений TUI всегда на месте
        return []
    state = resolve(style, data)
    placed = panel.placed(style, panel_data)
    if not state["icons"] and not state["dock"] and not ({"launcher", "search", "apps"} & set(placed)):
        return ["Нет ни значков, ни дока, ни меню запуска или быстрого запуска на панели: приложения на этой ОС открыть нечем, кроме ссылок и хуков."]
    return []
