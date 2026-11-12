"""Элементы самого стола, которые ОС включает и выключает независимо от стиля (SystemType.widgets).

Панели раскладываются отдельно (machines/world/panel.py). Здесь то, что
просто показывается или прячется: значки, бегущая строка, всплывающие уведомления и дата у часов.
"""
from dataclasses import dataclass

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


def hidden_css(style, data):
    """CSS, который прячет выключенные родные элементы стиля."""
    state = resolve(style, data)
    off = [BY_KEY[key].hide for key, on in state.items() if not on and is_native(key, style) and BY_KEY[key].hide]
    return "".join(f"{selector}{{display:none!important}}" for selector in off)


def warnings(style, data, parts=None):
    """Предупреждения для Студии: например, приложения открыть нечем. parts — SystemType.style_parts."""
    from machines.world import panel, styles

    chosen = styles.clean_parts(parts)
    look = panel.of(style, chosen.get("panel"))["look"]
    if look in ("phosphor", "tui"):                 # главное меню прошивки и список приложений TUI всегда на месте
        return []
    placed = panel.placed_all(style, chosen.get("panel"), chosen.get("panel2"))
    if not resolve(style, data)["icons"] and not ({"launcher", "search", "apps", "allapps"} & set(placed)):
        return ["Нет ни значков, ни меню запуска или быстрого запуска на панелях: приложения на этой ОС открыть нечем, кроме ссылок и хуков."]
    return []
