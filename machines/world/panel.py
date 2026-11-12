"""Главная панель рабочего стола: вид, край, форма и три слота с элементами (SystemType.style_parts["panel"]).

Вид панели берётся у одного из стилей (его разметка и CSS: desktop/panels/<вид>.html, static/ui/parts/panel/<вид>.css).
Слоты «начало», «центр» и «конец» перечисляют элементы по порядку; каждый элемент стоит не больше одного раза.

Элемент рисуется родной разметкой вида (desktop/panels/<вид>/<элемент>.html), если она есть и элемент стоит там, где вид
его рисует сам (NATIVE: слоты и край). Иначе вставляется общий элемент (desktop/elements/<элемент>.html), который вид
дорисовывает в своём стиле ([data-panel] .el-… в desktop/static/desktop/elements.css). Так прибитые к экрану часы Aether или
Modern не остаются на старом месте, когда их переносят.

Поведение одно на всех (desktop/static/desktop/shell.js) по атрибутам data-shell.
"""
from dataclasses import dataclass

SLOTS = {"start": "Начало", "center": "Центр", "end": "Конец"}
EDGES = {"top": "Сверху", "bottom": "Снизу"}           # без панели нельзя: на ней выход из сеанса
FORMS = {"bar": "Во всю ширину", "island": "Остров по центру"}


@dataclass(frozen=True)
class Element:
    key: str
    label: str
    hint: str


ELEMENTS = (
    Element("brand", "Название системы", "Имя ОС или марка устройства."),
    Element("launcher", "Меню запуска", "Кнопка со списком приложений и выходом из сеанса."),
    Element("tasks", "Панель задач", "Открытые окна пунктами."),
    Element("search", "Поиск приложений", "Поле поиска: набор открывает меню запуска с найденным."),
    Element("workspaces", "Рабочие столы", "Переключатель столов 1–4: окна живут на своём столе."),
    Element("apps", "Быстрый запуск", "Значки приложений прямо на панели, запущенные отмечены."),
    Element("notices", "Уведомления", "Кнопка журнала сообщений со счётчиком."),
    Element("console", "Кнопка консоли", "Быстро открыть и свернуть терминал."),
    Element("machine", "Сеанс", "Логин и машина; меню с выходом."),
    Element("actions", "Кнопки сеанса", "Сеансы, сброс раскладки, выход."),
    Element("ping", "Пинг", "Индикатор задержки связи."),
    Element("clock", "Часы", "Время и дата в поясе машины."),
)
BY_KEY = {element.key: element for element in ELEMENTS}
EXITS = ("launcher", "machine", "actions")          # где игрок найдёт выход из сеанса

LOOKS = ("aether", "classic", "modern", "gnome", "workbench", "tui", "phosphor")
LOOK_OF_STYLE = {"glitched": "aether"}

PRESETS = {
    "aether": {"edge": "top", "form": "bar", "start": ["machine"], "center": ["clock"], "end": ["ping"]},
    "classic": {"edge": "top", "form": "bar", "start": ["launcher", "tasks"], "center": [], "end": ["ping", "clock"]},
    "modern": {"edge": "bottom", "form": "bar", "start": ["launcher", "tasks"], "center": [], "end": ["ping", "notices", "clock"]},
    "gnome": {"edge": "top", "form": "bar", "start": ["launcher"], "center": ["clock"], "end": ["ping", "machine"]},
    "workbench": {"edge": "bottom", "form": "island", "start": ["clock", "workspaces", "apps", "actions"], "center": [], "end": ["ping"]},
    "tui": {"edge": "top", "form": "bar", "start": ["brand", "tasks"], "center": [], "end": ["ping", "clock"]},
    "phosphor": {"edge": "top", "form": "bar", "start": ["brand"], "center": [], "end": ["ping", "clock"]},
}

# родная разметка вида: элемент -> (в каких слотах, на каком крае, в какой форме; None — где угодно)
_ANY = (None, None, None)
NATIVE = {
    "aether": {"machine": _ANY, "ping": _ANY, "clock": (("center",), ("top",), ("bar",))},
    "classic": {"launcher": _ANY, "tasks": _ANY, "ping": _ANY, "clock": _ANY},
    "modern": {"launcher": _ANY, "tasks": _ANY, "ping": _ANY, "notices": _ANY, "clock": (("end",), ("bottom",), ("bar",))},
    "gnome": {"launcher": _ANY, "ping": _ANY, "machine": _ANY, "clock": (("center",), ("top",), ("bar",))},
    "workbench": {"clock": _ANY, "workspaces": _ANY, "apps": _ANY, "actions": _ANY, "ping": _ANY},
    "tui": {"brand": _ANY, "tasks": _ANY, "ping": _ANY, "clock": _ANY},
    "phosphor": {"brand": _ANY, "ping": _ANY, "clock": _ANY},
}
# своё меню запуска и свой журнал сообщений у вида (иначе их всплывающие панели добавляет стол)
NATIVE_LAUNCHER_PANEL = {"classic", "modern", "gnome", "tui"}
NATIVE_NOTICES_PANEL = {"classic", "modern", "gnome", "workbench", "tui", "phosphor"}
# у этих видов выход есть вне панели: полоса F-клавиш, главное меню прошивки
EXIT_OUTSIDE = {"tui", "phosphor"}
# у этих видов панель — строка состояния сверху, а снизу своя полоса: край не меняется
FIXED_EDGE = {"tui", "phosphor"}


def look_of(style):
    from machines.world import styles

    if style in LOOKS:
        return style
    return LOOK_OF_STYLE.get(style, styles.DEFAULT_STYLE)


def clean(data):
    """Только известное: {"look", "edge", "form", "start", "center", "end"}; элемент не больше одного раза."""
    if not isinstance(data, dict):
        return {}
    out = {}
    if data.get("look") in LOOKS:
        out["look"] = data["look"]
    if data.get("edge") in EDGES:
        out["edge"] = data["edge"]
    if data.get("form") in FORMS:
        out["form"] = data["form"]
    seen = set()
    for slot in SLOTS:
        if isinstance(data.get(slot), list):
            keys = [key for key in data[slot] if key in BY_KEY and key not in seen]
            seen.update(keys)
            out[slot] = keys
    return out


def problems(style, data):
    """Ошибки раскладки панели для Студии: неизвестное, повторы, нет выхода из сеанса."""
    found = []
    if not isinstance(data, dict):
        return ["Панель задаётся объектом."]
    for name, choices, label in (("look", LOOKS, "вида панели"), ("edge", EDGES, "края"), ("form", FORMS, "формы")):
        if name in data and data[name] not in choices:
            found.append(f"Нет такого {label}: {data[name]}.")
    seen = set()
    for slot in SLOTS:
        for key in data.get(slot) or []:
            if key not in BY_KEY:
                found.append(f"Нет такого элемента панели: {key}.")
            elif key in seen:
                found.append(f"{BY_KEY[key].label}: стоит на панели дважды.")
            seen.add(key)
    if not found and not exits(style, data):
        found.append("На панели нет выхода из сеанса: оставьте меню запуска, «Сеанс» или «Кнопки сеанса».")
    return found


def of(style, data=None):
    """Панель ОС: заготовка вида, поверх неё выбор автора. Вид меняет заготовку раскладки целиком."""
    chosen = clean(data)
    look = chosen.get("look", look_of(style))
    found = {"look": look, **PRESETS[look], **{key: value for key, value in chosen.items() if key != "look"}}
    if look in FIXED_EDGE:
        found["edge"] = PRESETS[look]["edge"]
    return found


def exits(style, data=None):
    panel = of(style, data)
    if panel["look"] in EXIT_OUTSIDE:
        return True
    return any(key in panel[slot] for slot in SLOTS for key in EXITS)


def native(look, key, slot, edge, form="bar"):
    rule = NATIVE.get(look, {}).get(key)
    if rule is None:
        return False
    slots, edges, forms = rule
    return (slots is None or slot in slots) and (edges is None or edge in edges) and (forms is None or form in forms)


def attrs(style, data=None):
    """{атрибут без data-: значение} для <html>: вид, край, форма и разворот (край не тот, на который вид рассчитан)."""
    panel = of(style, data)
    preset = PRESETS[panel["look"]]
    out = {"panel": panel["look"], "panel-edge": panel["edge"], "panel-form": panel["form"]}
    if panel["edge"] != preset["edge"]:
        out["panel-flip"] = panel["edge"]
    if panel["form"] != preset["form"]:
        out["panel-reform"] = panel["form"]
    return out


def elements(style, data=None):
    """{слот: [(ключ, шаблон)]} для шаблона вида панели."""
    panel = of(style, data)
    look, edge, form = panel["look"], panel["edge"], panel["form"]
    return {slot: [(key, f"desktop/panels/{look}/{key}.html" if native(look, key, slot, edge, form) else f"desktop/elements/{key}.html")
                   for key in panel[slot]] for slot in SLOTS}


def placed(style, data=None):
    """{элемент: слот} для всего, что стоит на панели."""
    panel = of(style, data)
    return {key: slot for slot in SLOTS for key in panel[slot]}
