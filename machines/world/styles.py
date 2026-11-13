"""Стиль рабочего стола и окон по ОС: выбор из готовых стилей и переопределение токенов.

Стиль это готовый CSS (static/ui/themes/<слаг>.css), в котором лежит всё, что не выражается переменными: раскладка панели, вид и порядок
кнопок окна, иконки. Стили пишутся в коде и перечислены здесь; автору ОС остаётся выбрать один и, если нужно, переназначить токены
(цвета, шрифты, форму: static/ui/tokens.css). Значения токенов проверяются по типу, так что в страницу попадает только безопасный CSS."""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

DEFAULT_STYLE = "aether"


@dataclass(frozen=True)
class Style:
    label: str
    description: str
    css: bool = False       # есть файл static/ui/themes/<слаг>.css поверх токенов (у основного стиля нет)
    shell: bool = False     # свой вид панели и стола (machines/world/panel.py, desktop/panels/<слаг>.html); иначе как у aether


STYLES = {
    "aether": Style("Aether", "Тёмный рабочий стол Aether: острые углы, рамка 1px, заголовок вкладкой над окном."),
    "modern": Style("Modern", "Современный оконный стол: панель задач снизу, скруглённые окна с заголовком внутри и кнопками справа, плитки-иконки.", css=True, shell=True),
    "phosphor": Style("Phosphor", "Прошивка устройства на монохромном ЖК: главное меню и панель сведений, приложение на весь экран (Esc назад), растровый шрифт, пиксельная сетка, выбор инверсией.", css=True, shell=True),
    "classic": Style("Classic", "Обобщённая ОС начала 90-х: растровый шрифт, крем и чернила с одним акцентом, дизеринг вместо градиентов, плоские контуры с жёсткой тенью, одна верхняя панель с окнами в виде пунктов.", css=True, shell=True),
    "workbench": Style("Workbench", "Лабораторная Unix-станция: передняя панель снизу по центру (часы, четыре рабочих стола, запуски, выход), окна с толстой рамкой из двух тонких линий, гравированные поля вместо объёма.", css=True, shell=True),
    "tui": Style("Terminal UI", "Монохромный BIOS: меню сверху, окна в двойной рамке, инверсия вместо цвета, полоса F-клавиш снизу, шрифт терминала.", css=True, shell=True),
    "gnome": Style("GNOME", "Современный стол в духе GNOME: тонкая верхняя панель с часами по центру, окна с крупными скруглениями и круглыми кнопками, плитки-приложения, мягкие тени.", css=True, shell=True),
    "glitched": Style("Glitched", "Сломанный Aether: та же оболочка, но мёртвая палитра с кислотным акцентом, цветные сдвиги у яркого текста и рамок, линии развёртки и редкая полоса помех, заголовки окон иногда дёргаются.", css=True),
}


@dataclass(frozen=True)
class Token:
    name: str
    label: str
    group: str
    kind: str          # color | font | length
    hint: str = ""     # где это видно на столе, одной строкой (его показывает Студия)


TOKENS = (
    Token("--bg", "Фон рабочего стола и страниц", "Цвета", "color", "Цвет самого стола за значками и окон-страниц: вики, почты, карты."),
    Token("--panel", "Панели, окна, карточки", "Цвета", "color", "Заливка окон, верхней панели и карточек. Второй по площади цвет после фона."),
    Token("--fg", "Основной текст", "Цвета", "color", "Обычный текст в окнах и подписи значков."),
    Token("--font-light", "Яркий текст, заголовки", "Цвета", "color", "Заголовки окон и выделенный текст: ярче основного."),
    Token("--font-dark", "Текст на светлых плашках", "Цвета", "color", "Надпись на светлых и акцентных кнопках и плашках (например «OK»)."),
    Token("--font-soft", "Второстепенный текст", "Цвета", "color", "Пояснения и подписи рядом с основным текстом."),
    Token("--font-muted", "Приглушённый текст", "Цвета", "color", "Самый тихий текст: подсказки, недоступное, подписи к времени."),
    Token("--line", "Разделители", "Линии", "color", "Тонкие линии между блоками в окнах: вики, мониторинг."),
    Token("--line-faint", "Еле заметные линии и сетка стола", "Линии", "color", "Сетка рабочего стола и линии на экране загрузки. Узор «Сетка» берёт цвет отсюда."),
    Token("--line-bright", "Яркие разделители и рамки полей", "Линии", "color", "Рамки полей ввода и кнопок, заметные разделители."),
    Token("--window-border", "Рамка окон", "Линии", "color", "Внешняя рамка окна на рабочем столе."),
    Token("--accent", "Акцент", "Акценты", "color", "Главный цвет интерфейса: ссылки, выбранное, активные элементы."),
    Token("--accent-green", "Зелёный акцент", "Акценты", "color", "Хорошие статусы: связь есть, успех, индикатор связи на панели."),
    Token("--accent-warn", "Предупреждение", "Акценты", "color", "Жёлтые предупреждения и метки «стоит обратить внимание»."),
    Token("--accent-error", "Ошибка", "Акценты", "color", "Красные ошибки и окна «Access denied»."),
    Token("--accent-error-darker", "Ошибка, тёмнее", "Акценты", "color", "Тёмный оттенок ошибки: рамки и тени красных окон."),
    Token("--term-fg", "Терминал: текст", "Терминал", "color", "Основной текст в консоли терминала и на экране входа."),
    Token("--term-dim", "Терминал: тусклый", "Терминал", "color", "Подсказки и второстепенные строки в консоли (например приглашение)."),
    Token("--term-ok", "Терминал: успех", "Терминал", "color", "Метка [ ok ] и успешные строки в консоли."),
    Token("--term-warn", "Терминал: предупреждение", "Терминал", "color", "Метка [warn] и предупреждающие строки в консоли."),
    Token("--term-error", "Терминал: ошибка", "Терминал", "color", "Метка [fail] и строки с ошибками в консоли."),
    Token("--term-info", "Терминал: сведения", "Терминал", "color", "Метка [info] и справочные строки в консоли."),
    Token("--font-main", "Основной шрифт", "Шрифты", "font", "Шрифт всего интерфейса: окна, панель, подписи."),
    Token("--font-console", "Шрифт терминала", "Шрифты", "font", "Моноширинный шрифт консоли терминала и экрана входа."),
    Token("--fs-console", "Размер шрифта терминала", "Шрифты", "length", "Размер букв в консоли (например 14px)."),
    Token("--radius", "Скругление углов", "Форма", "length", "Насколько скруглены углы окон, кнопок и карточек (0px: острые)."),
    Token("--border-w", "Толщина рамок", "Форма", "length", "Толщина рамок окон и полей."),
    Token("--ctl-radius", "Скругление кнопок и полей", "Форма", "length", "Углы кнопок, полей и меток внутри приложений: вики, почта, карта, просмотрщики (0px: острые)."),
    Token("--ctl-border", "Толщина рамки кнопок и полей", "Форма", "length", "Рамка кнопок, полей и меток внутри приложений."),
    Token("--ctl-shade", "Тень кнопок", "Форма", "length", "Жёсткая тень кнопок внутри приложений: на сколько она сдвинута вправо и вниз (0px: без тени)."),
    Token("--scroll-w", "Ширина полосы прокрутки", "Форма", "length", "Полоса прокрутки в приложениях и просмотрщиках."),
    Token("--tab-h", "Высота заголовка окна", "Форма", "length", "Высота полосы с названием и кнопками у окна."),
    Token("--cell", "Шаг сетки рабочего стола", "Форма", "length", "Размер клетки сетки стола. Узор «Сетка» и значки выравниваются по нему."),
    Token("--title-bg", "Фон заголовка", "Заголовок окна", "color", "Полоса или вкладка с названием окна. Пусто: как у выбранного заголовка."),
    Token("--title-fg", "Текст заголовка", "Заголовок окна", "color", "Название окна, его кнопки; у заголовка из символов — сами символы рамки."),
    Token("--title-bg-active", "Фон активного заголовка", "Заголовок окна", "color", "То же у окна, в котором сейчас работают."),
    Token("--title-fg-active", "Текст активного заголовка", "Заголовок окна", "color", "Название и кнопки активного окна."),
)
BY_NAME = {token.name: token for token in TOKENS}

_COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|(rgb|rgba|hsl|hsla)\([0-9\s,.%/]+\))$")
_LENGTH = re.compile(r"^-?\d+(\.\d+)?(px|rem|em|%)?$")
_FONT = re.compile(r"^var\((--ff-[a-z0-9-]+)\)$")


@lru_cache(maxsize=1)
def _defaults():
    """Значения по умолчанию из static/ui/tokens.css: первый блок :root."""
    text = (Path(settings.BASE_DIR) / "static" / "ui" / "tokens.css").read_text()
    block = text[text.index(":root {"):]
    return {name: value.strip() for name, value in re.findall(r"(--[a-z0-9-]+):\s*([^;]+);", block)}


def defaults():
    return _defaults()


@lru_cache(maxsize=None)
def style_defaults(slug):
    """Значения токенов у стиля: общие из tokens.css, поверх них первый блок :root из static/ui/themes/<слаг>.css (если он есть)."""
    values = dict(_defaults())
    style = STYLES.get(slug)
    path = Path(settings.BASE_DIR) / "static" / "ui" / "themes" / f"{slug}.css"
    if style is not None and style.css and path.exists():
        found = re.search(r":root \{(.*?)\n\}", path.read_text(), re.S)
        if found:
            block = re.sub(r"/\*.*?\*/", "", found.group(1), flags=re.S)
            values.update({name: value.strip() for name, value in re.findall(r"(--[a-z0-9-]+):\s*([^;]+);", block)})
    return values


# Части стиля, которые пока целиком берутся у стиля: файл static/ui/parts/<часть>/<стиль>.css включает атрибут data-<часть> на <html>.
PARTS = {
    "notice": "Сообщения и уведомления",
    "panel": "Панель",
    "dock": "Док",
}

# Окна собираются из параметров (static/ui/parts/windows.css, атрибуты data-win-<параметр>). Первый вариант в списке не значит
# «по умолчанию»: умолчания задаёт стиль (WINDOW_PRESETS), автор ОС меняет любой параметр по отдельности (SystemType.style_parts).
WINDOW = {
    "title": ("Заголовок", {
        "tab": "Вкладка над окном",
        "bar": "Полоса во всю ширину",
        "center": "В цвет окна, название по центру",
        "plaque": "Штриховка и табличка с названием",
        "raised": "Полоса с обводкой (как Workbench)",
        "ascii": "Строка рамки из символов, как в TUI",
        "full": "Приложение на весь экран",
    }),
    "hatch": ("Узор штриховки", {"lines": "Горизонтальные линии", "diagonal": "Диагональ ////"}),
    "frame": ("Рамка", {
        "line": "Тонкая линия",
        "soft": "Скругление и мягкая тень",
        "hard": "Контур с жёсткой тенью",
        "double": "Две тонкие линии",
        "ascii": "Из символов, как в TUI",
        "none": "Без рамки",
    }),
    "side": ("Кнопки окна", {"left": "Слева", "right": "Справа"}),
    "buttons": ("Вид кнопок", {
        "icons": "Значки × □ –",
        "squares": "Широкие поля",
        "circles": "Кружки",
        "traffic": "Цветные кружки",
        "dots": "Точки в пазу",
        "boxes": "Коробочки",
        "text": "Текст [x]",
    }),
    "set": ("Набор кнопок", {"all": "Закрыть, развернуть, свернуть", "close": "Только закрыть"}),
}

_AETHER_WINDOW = {"title": "tab", "hatch": "lines", "frame": "line", "side": "left", "buttons": "icons", "set": "all"}
WINDOW_PRESETS = {
    "aether": _AETHER_WINDOW,
    "glitched": _AETHER_WINDOW,
    "modern": {"title": "bar", "hatch": "lines", "frame": "soft", "side": "right", "buttons": "squares", "set": "all"},
    "gnome": {"title": "center", "hatch": "lines", "frame": "soft", "side": "right", "buttons": "circles", "set": "all"},
    "classic": {"title": "plaque", "hatch": "lines", "frame": "hard", "side": "right", "buttons": "boxes", "set": "all"},
    "workbench": {"title": "raised", "hatch": "lines", "frame": "double", "side": "right", "buttons": "dots", "set": "all"},
    "tui": {"title": "ascii", "hatch": "lines", "frame": "ascii", "side": "right", "buttons": "text", "set": "all"},
    "phosphor": {"title": "full", "hatch": "lines", "frame": "none", "side": "right", "buttons": "text", "set": "close"},
}


_LOOK_LABELS = {"aether": "Aether", "classic": "Classic", "modern": "Modern", "gnome": "GNOME", "workbench": "Workbench", "tui": "Terminal UI", "phosphor": "Phosphor"}

# «Быстрый запуск» (элемент любой панели), сообщения и часы: те же параметры с вариантами, умолчания берутся у вида панели стиля (machines/world/panel.py, look_of)
APPS = {
    "size": ("Размер значков", {"s": "Мелкие", "m": "Средние", "l": "Крупные"}),
    "labels": ("Подписи", {"none": "Нет", "hover": "При наведении", "always": "Всегда"}),
    "mark": ("Метка запущенных", {"dot": "Точка", "line": "Черта", "glow": "Подсветка"}),
}
NOTICE = {
    "look": ("Вид сообщений", _LOOK_LABELS),
    "corner": ("Угол уведомлений", {"br": "Справа снизу", "tr": "Справа сверху", "tc": "Сверху по центру", "bl": "Слева снизу", "tl": "Слева сверху"}),
    "errors": ("Ошибки", {"window": "Окном", "banner": "Полосой сверху", "screen": "На весь экран"}),
    "fill": ("Цвет окна ошибки", {"standard": "Стандартный", "fill": "Заливка"}),
}
CLOCK = {
    "hours": ("Формат", {"24": "24 часа", "12": "12 часов"}),
    "seconds": ("Секунды", {"on": "Показывать", "off": "Нет"}),
}
_ONOFF = {"off": "Нет", "on": "Есть"}
FX = {
    "scanlines": ("Строки развёртки", _ONOFF),
    "noise": ("Шум сигнала", _ONOFF),
    "glow": ("Свечение текста", _ONOFF),
    "pixels": ("Пиксельная сетка", _ONOFF),
    "glitch": ("Сбои кадра", _ONOFF),
}
ICONS = {
    "set": ("Набор значков", {"style": "Как в стиле", **{slug: label for slug, label in _LOOK_LABELS.items() if slug != "tui"}, "text": "Без картинок, текстом"}),
    "look": ("Вид значков", {"style": "Как в стиле", "tile": "Плитка", "outline": "Контур", "ascii": "Только знак"}),
}
CURSOR = {
    "cursor": ("Курсор", {"default": "Обычный", "block": "Блочный", "cross": "Перекрестие"}),
}
GROUPS = {"window": WINDOW, "apps": APPS, "notice": NOTICE, "clock": CLOCK, "fx": FX, "icons": ICONS, "cursor": CURSOR}
GROUP_LABELS = {"window": "окон", "apps": "быстрого запуска", "notice": "сообщений", "clock": "часов", "fx": "эффектов", "icons": "значков", "cursor": "курсора"}

_DEFAULTS = {
    "apps": {"size": "m", "labels": "hover", "mark": "dot"},
    "notice": {"corner": "br", "errors": "window", "fill": "standard"},
    "clock": {"hours": "24", "seconds": "on"},
    "fx": {"scanlines": "off", "noise": "off", "glow": "off", "pixels": "off", "glitch": "off"},
    "icons": {"set": "style", "look": "style"},
    "cursor": {"cursor": "default"},
}
_STYLE_PRESETS = {                       # у стилей, которые не совпадают с видом панели (Glitched — это Aether со сбоями)
    "fx": {"glitched": {"glitch": "on"}, "phosphor": {"pixels": "on"}},
}
_LOOK_PRESETS = {
    "apps": {"gnome": {"labels": "none"}},
    "notice": {"gnome": {"corner": "tc"}},
}


def preset(group, slug):
    """Параметры группы у стиля (без выбора автора)."""
    from machines.world import panel

    if group == "window":
        return dict(WINDOW_PRESETS.get(slug, _AETHER_WINDOW))
    look = panel.look_of(slug)
    found = {**_DEFAULTS[group], **_LOOK_PRESETS.get(group, {}).get(look, {}), **_STYLE_PRESETS.get(group, {}).get(slug, {})}
    if group == "notice":
        found["look"] = look
    return found


def group_of(group, slug, custom=None):
    """{параметр: вариант} группы: заготовка стиля, поверх неё выбор автора ОС."""
    chosen = clean_parts(custom).get(group, {})
    base = preset(group, chosen["look"]) if group == "notice" and "look" in chosen else preset(group, slug)     # чужой вид сообщений — с его углом
    return {**base, **chosen}


def clean_parts(data):
    """Только известное: {"window"|"dock"|"notice"|"clock": {параметр: вариант}, "panel": {...}}; пустые разделы отбрасываются."""
    from machines.world import panel

    if not isinstance(data, dict):
        return {}
    out = {}
    for group, params in GROUPS.items():
        chosen = data.get(group)
        found = {key: value for key, value in chosen.items() if key in params and value in params[key][1]} if isinstance(chosen, dict) else {}
        if found:
            out[group] = found
    found = panel.clean(data.get("panel"))
    if found:
        out["panel"] = found
    found = panel.clean2(data.get("panel2"))
    if found:
        out["panel2"] = found
    from machines.world import cards

    found = cards.clean(data.get("cards"))
    if found is not None:                           # пустой список — «карточек нет», это тоже выбор
        out["cards"] = found
    return out


def parts_problems(data):
    found = []
    for group, params in GROUPS.items():
        chosen = (data or {}).get(group) or {}
        for key, value in chosen.items() if isinstance(chosen, dict) else ():
            if key not in params:
                found.append(f"У {GROUP_LABELS[group]} нет параметра {key}.")
            elif value not in params[key][1]:
                found.append(f"{params[key][0]}: нет варианта «{value}».")
    return found


def window_of(slug, custom=None):
    """{параметр окна: вариант}: заготовка стиля, поверх неё выбор автора ОС."""
    return group_of("window", slug, custom)


def parts(slug, custom=None):
    """{атрибут без data-: значение} для <html>: параметры окон, дока, сообщений и часов, панель (machines/world/panel.py)."""
    from machines.world import panel

    attrs = {f"win-{key}": value for key, value in window_of(slug, custom).items()}
    found = panel.attrs(slug, clean_parts(custom).get("panel"))
    notice = group_of("notice", slug, custom)
    attrs.update({"notice": notice["look"], "panel": found["panel"], "dock": found["panel"]})       # дополнительную панель дорисовывает вид главной
    attrs.update(found)
    chosen = clean_parts(custom)
    attrs.update(panel.attrs2(slug, chosen.get("panel2"), chosen.get("panel")))
    attrs.update({f"apps-{key}": value for key, value in group_of("apps", slug, custom).items()})
    attrs["toast-corner"] = notice["corner"]
    if notice["corner"] != preset("notice", notice["look"])["corner"]:
        attrs["toast-move"] = "1"                   # угол не тот, под который рассчитан вид сообщений
    attrs["error-form"] = notice["errors"]
    attrs["error-fill"] = notice["fill"]
    attrs.update({f"clock-{key}": value for key, value in group_of("clock", slug, custom).items()})
    attrs.update({f"fx-{key}": value for key, value in group_of("fx", slug, custom).items()})
    attrs["icons-look"] = group_of("icons", slug, custom)["look"]
    attrs["cursor"] = group_of("cursor", slug, custom)["cursor"]
    return attrs


@lru_cache(maxsize=None)
def part_file(part, kind):
    """Путь к файлу части в static (ui/parts/<часть>/<вид>.css) или пусто, если у этого вида своего файла нет."""
    rel = f"ui/parts/{part}/{kind}.css"
    return rel if (Path(settings.BASE_DIR) / "static" / rel).exists() else ""


def fonts():
    """Гарнитуры, из которых выбирается шрифт: var(--ff-…) -> подпись."""
    return {f"var({name})": name[len("--ff-"):].replace("-", " ") for name in _defaults() if name.startswith("--ff-")}


def problems(style, tokens):
    """Ошибки выбора стиля и значений токенов: список строк."""
    found = []
    if style not in STYLES:
        found.append(f"Нет такого стиля: {style}.")
    for name, value in (tokens or {}).items():
        token = BY_NAME.get(name)
        value = str(value).strip()
        if token is None:
            found.append(f"Токен {name} не переопределяется.")
        elif token.kind == "color" and not _COLOR.match(value):
            found.append(f"{name}: цвет пишется как #1a2b3c или rgb(26, 43, 60), а не «{value}».")
        elif token.kind == "length" and not _LENGTH.match(value):
            found.append(f"{name}: размер пишется как 4px, 0.5rem или 0, а не «{value}».")
        elif token.kind == "font" and not (_FONT.match(value) and value in fonts()):
            found.append(f"{name}: шрифт выбирается из списка, а не «{value}».")
    return found


def css(tokens):
    """Переопределения токенов одним блоком :root (пусто, если переопределять нечего)."""
    rows = [f"{name}: {str(value).strip()};" for name, value in (tokens or {}).items() if name in BY_NAME and str(value).strip()]
    return ":root { " + " ".join(rows) + " }" if rows else ""
