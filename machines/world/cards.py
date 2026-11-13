"""Карточки на столе: часы, система, почта, события и эфир по углам (SystemType.style_parts["cards"]).

Порядок карточек в списке — порядок в углу сверху вниз. Заготовка берётся у вида панели стиля (у Modern — система и почта
в правом верхнем углу); автор ОС задаёт свой список целиком. Разметка — desktop/elements/cards.html, вид — static/ui/parts/cards.css,
значения подставляет shell.js по data-widget.
"""
CARDS = {
    "clock": ("Часы", "Крупные часы и дата в поясе машины."),
    "system": ("Система", "Хост, ОС, пользователь, связь, длительность сеанса и число окон."),
    "mail": ("Почта", "Непрочитанные письма; карточка видна, только когда они есть."),
    "events": ("События", "Ближайшие моменты мира, как в команде at: идущие и скорые с обратным отсчётом."),
    "air": ("Эфир", "Частота, на которой стоит игрок, и последнее, что он услышал."),
}
CORNERS = {"tr": "Справа сверху", "tl": "Слева сверху", "br": "Справа снизу", "bl": "Слева снизу"}
PRESETS = {"modern": [{"key": "system", "corner": "tr"}, {"key": "mail", "corner": "tr"}]}


def clean(data):
    """[{"key", "corner"}] без повторов и неизвестного; None — не задано (как в стиле)."""
    if not isinstance(data, list):
        return None
    out, seen = [], set()
    for item in data:
        if isinstance(item, dict) and item.get("key") in CARDS and item.get("corner") in CORNERS and item["key"] not in seen:
            seen.add(item["key"])
            out.append({"key": item["key"], "corner": item["corner"]})
    return out


def problems(data):
    if not isinstance(data, list):
        return ["Карточки задаются списком."]
    found, seen = [], set()
    for item in data:
        key, corner = (item.get("key"), item.get("corner")) if isinstance(item, dict) else (None, None)
        if key not in CARDS:
            found.append(f"Нет такой карточки: {key}.")
        elif corner not in CORNERS:
            found.append(f"{CARDS[key][0]}: нет такого угла {corner}.")
        elif key in seen:
            found.append(f"{CARDS[key][0]}: карточка стоит дважды.")
        seen.add(key)
    return found


def of(style, data=None):
    """Карточки ОС по порядку: выбор автора или заготовка вида панели стиля."""
    from machines.world import panel

    chosen = clean(data)
    return chosen if chosen is not None else [dict(item) for item in PRESETS.get(panel.look_of(style), [])]


def by_corner(style, data=None):
    """{угол: [ключ]} только для занятых углов, в порядке CORNERS."""
    found = {}
    for item in of(style, data):
        found.setdefault(item["corner"], []).append(item["key"])
    return {corner: found[corner] for corner in CORNERS if corner in found}
