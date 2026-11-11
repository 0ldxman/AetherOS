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
    shell: bool = False     # своя оболочка рабочего стола: шаблон desktop/shells/<слаг>.html (иначе общая, aether)


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
    Token("--tab-h", "Высота заголовка окна", "Форма", "length", "Высота полосы с названием и кнопками у окна."),
    Token("--cell", "Шаг сетки рабочего стола", "Форма", "length", "Размер клетки сетки стола. Узор «Сетка» и значки выравниваются по нему."),
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
