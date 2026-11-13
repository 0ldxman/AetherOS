"""Панели рабочего стола: главная (SystemType.style_parts["panel"]) и дополнительная (style_parts["panel2"]).

Главная: вид, край (сверху или снизу), форма и три слота с элементами; она занимает полосу стола.
Дополнительная — то, что раньше было доком: есть или нет, край (любой из четырёх), форма, автоскрытие и те же три слота.
Она висит поверх стола в оформлении вида главной (static/ui/parts/dock/<вид>.css) и рисует только общие элементы.
Каждый элемент стоит не больше чем в одной панели и не больше одного раза.


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
EDGES = {"top": "Сверху", "bottom": "Снизу", "left": "Слева", "right": "Справа"}
FORMS = {"bar": "Полоса во всю ширину", "dock": "Док по центру", "islands": "Острова"}
SHOW = {"on": "Есть", "off": "Нет"}
HIDE = {"off": "Нет", "on": "Прячется, пока не подвести мышь"}
RESERVE = {"off": "Висит поверх окон", "on": "Окна не заходят под неё"}
LEGACY_FORMS = {"island": "dock"}                     # прежнее «остров» — это док


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
    Element("apps", "Быстрый запуск", "Значки приложений прямо на панели, запущенные отмечены. Размер, подписи и метка — в «Быстром запуске»."),
    Element("allapps", "Все приложения", "Кнопка-сетка: открывает меню запуска со всеми приложениями."),
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
    "workbench": {"edge": "bottom", "form": "dock", "start": ["clock", "workspaces", "apps", "actions"], "center": [], "end": ["ping"]},
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
    form = LEGACY_FORMS.get(data.get("form"), data.get("form"))
    if form in FORMS:
        out["form"] = form
    if data.get("show") in SHOW:
        out["show"] = data["show"]
    seen = set()
    for slot in SLOTS:
        if isinstance(data.get(slot), list):
            keys = [key for key in data[slot] if key in BY_KEY and key not in seen]
            seen.update(keys)
            out[slot] = keys
    return out


def problems(style, data, data2=None):
    """Ошибки раскладки панели для Студии: неизвестное, повторы, нет выхода из сеанса."""
    found = []
    if not isinstance(data, dict):
        return ["Панель задаётся объектом."]
    data = {**data, "form": LEGACY_FORMS.get(data["form"], data["form"])} if "form" in data else data
    for name, choices, label in (("look", LOOKS, "вида панели"), ("show", SHOW, "значения «есть»"), ("edge", EDGES, "края"), ("form", FORMS, "формы")):
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
    if not found and not exits(style, data, data2):
        found.append("На панелях нет выхода из сеанса: оставьте меню запуска, «Сеанс» или «Кнопки сеанса».")
    return found


def of(style, data=None):
    """Панель ОС: заготовка вида, поверх неё выбор автора. Вид меняет заготовку раскладки целиком."""
    chosen = clean(data)
    look = chosen.get("look", look_of(style))
    found = {"look": look, "show": "on", **PRESETS[look], **{key: value for key, value in chosen.items() if key != "look"}}
    if look in FIXED_EDGE:
        found["edge"] = PRESETS[look]["edge"]
    return found


def exits(style, data=None, data2=None):
    """Есть ли выход из сеанса: у вида вне панели, на главной или на показанной дополнительной."""
    if of(style, data)["look"] in EXIT_OUTSIDE:
        return True
    return any(key in placed_all(style, data, data2) for key in EXITS)


def native(look, key, slot, edge, form="bar"):
    rule = NATIVE.get(look, {}).get(key)
    if rule is None or edge in ("left", "right"):       # родная разметка видов рассчитана на горизонтальную панель
        return False
    slots, edges, forms = rule
    return (slots is None or slot in slots) and (edges is None or edge in edges) and (forms is None or form in forms)


def attrs(style, data=None):
    """{атрибут без data-: значение} для <html>: вид, край, форма и разворот (край не тот, на который вид рассчитан)."""
    panel = of(style, data)
    preset = PRESETS[panel["look"]]
    out = {"panel": panel["look"], "panel-show": panel["show"], "panel-edge": panel["edge"], "panel-form": panel["form"]}
    if panel["edge"] != preset["edge"]:
        out["panel-flip"] = panel["edge"]
    if panel["form"] != preset["form"]:
        out["panel-reform"] = panel["form"]
    return out


def elements(style, data=None):
    """{слот: [(ключ, шаблон)]} для шаблона вида панели."""
    panel = of(style, data)
    if panel["show"] == "off":                      # выключенная основная ничего не рисует: её элементы могут стоять на дополнительной
        return {slot: [] for slot in SLOTS}
    look, edge, form = panel["look"], panel["edge"], panel["form"]
    return {slot: [(key, f"desktop/panels/{look}/{key}.html" if native(look, key, slot, edge, form) else f"desktop/elements/{key}.html")
                   for key in panel[slot]] for slot in SLOTS}


def taken_by_main(style, data=None):
    """Что занято основной панелью: её элементы, если она есть (выключенная ничего не держит)."""
    return placed(style, data) if of(style, data)["show"] == "on" else {}


def placed(style, data=None):
    """{элемент: слот} для всего, что стоит на панели."""
    panel = of(style, data)
    return {key: slot for slot in SLOTS for key in panel[slot]}


# ---------- дополнительная панель (раньше док) ----------
EDGES2 = {"bottom": "Снизу", "top": "Сверху", "left": "Слева", "right": "Справа"}
FORMS2 = {"bar": "Полоса во всю длину края", "dock": "Док по центру", "islands": "Острова"}
PRESET2 = {"show": "off", "edge": "bottom", "form": "dock", "hide": "off", "reserve": "off", "start": ["apps"], "center": [], "end": []}
PRESETS2 = {"gnome": {"show": "on", "end": ["allapps"]}}


def clean2(data):
    """Только известное у дополнительной панели: show, edge, form, hide и три слота."""
    if not isinstance(data, dict):
        return {}
    data = {**data, "form": LEGACY_FORMS.get(data["form"], data["form"])} if "form" in data else data
    out = {name: data[name] for name, choices in (("show", SHOW), ("edge", EDGES2), ("form", FORMS2), ("hide", HIDE), ("reserve", RESERVE)) if data.get(name) in choices}
    seen = set()
    for slot in SLOTS:
        if isinstance(data.get(slot), list):
            keys = [key for key in data[slot] if key in BY_KEY and key not in seen]
            seen.update(keys)
            out[slot] = keys
    return out


def of2(style, data=None, main=None):
    """Дополнительная панель: заготовка вида главной, поверх неё выбор автора; что стоит на главной, сюда не попадает."""
    look = of(style, main)["look"]
    found = {**PRESET2, **PRESETS2.get(look, {}), **clean2(data)}
    taken = set(taken_by_main(style, main))
    for slot in SLOTS:
        found[slot] = [key for key in found[slot] if key not in taken]
    return found


def problems2(style, data, main=None):
    found = []
    if not isinstance(data, dict):
        return ["Дополнительная панель задаётся объектом."]
    for name, choices, label in (("show", SHOW, "значения «есть»"), ("edge", EDGES2, "края"), ("form", FORMS2, "формы"), ("hide", HIDE, "автоскрытия"), ("reserve", RESERVE, "места")):
        if name in data and data[name] not in choices:
            found.append(f"Нет такого {label}: {data[name]}.")
    data = {**data, "form": LEGACY_FORMS.get(data["form"], data["form"])} if "form" in data else data
    taken, seen = set(taken_by_main(style, main)), set()
    for slot in SLOTS:
        for key in data.get(slot) or []:
            if key not in BY_KEY:
                found.append(f"Нет такого элемента панели: {key}.")
            elif key in seen:
                found.append(f"{BY_KEY[key].label}: стоит на панели дважды.")
            elif key in taken:
                found.append(f"{BY_KEY[key].label}: уже стоит на главной панели.")
            seen.add(key)
    return found


def attrs2(style, data=None, main=None):
    found = of2(style, data, main)
    return {"pl2-show": found["show"], "pl2-edge": found["edge"], "pl2-form": found["form"], "pl2-hide": found["hide"], "pl2-reserve": found["reserve"]}


def elements2(style, data=None, main=None):
    """{слот: [(ключ, шаблон)]} дополнительной панели: всегда общие элементы."""
    found = of2(style, data, main)
    return {slot: [(key, f"desktop/elements/{key}.html") for key in found[slot]] for slot in SLOTS}


def placed_all(style, main=None, data2=None):
    """{элемент: панель} по обеим панелям, которые есть."""
    out = {key: "panel" for key in taken_by_main(style, main)}
    found = of2(style, data2, main)
    if found["show"] == "on":
        out.update({key: "panel2" for slot in SLOTS for key in found[slot]})
    return out
