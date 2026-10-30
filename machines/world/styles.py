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
    "gnome": Style("GNOME", "Современный стол в духе GNOME: тонкая верхняя панель с часами по центру, окна с крупными скруглениями и круглыми кнопками, плитки-приложения, мягкие тени.", css=True, shell=True),
}


@dataclass(frozen=True)
class Token:
    name: str
    label: str
    group: str
    kind: str          # color | font | length


TOKENS = (
    Token("--bg", "Фон рабочего стола и страниц", "Цвета", "color"),
    Token("--panel", "Панели, окна, карточки", "Цвета", "color"),
    Token("--fg", "Основной текст", "Цвета", "color"),
    Token("--font-light", "Яркий текст, заголовки", "Цвета", "color"),
    Token("--font-dark", "Текст на светлых плашках", "Цвета", "color"),
    Token("--font-soft", "Второстепенный текст", "Цвета", "color"),
    Token("--font-muted", "Приглушённый текст", "Цвета", "color"),
    Token("--line", "Разделители", "Линии", "color"),
    Token("--line-faint", "Еле заметные линии и сетка стола", "Линии", "color"),
    Token("--line-bright", "Яркие разделители и рамки полей", "Линии", "color"),
    Token("--window-border", "Рамка окон", "Линии", "color"),
    Token("--accent", "Акцент", "Акценты", "color"),
    Token("--accent-green", "Зелёный акцент", "Акценты", "color"),
    Token("--accent-warn", "Предупреждение", "Акценты", "color"),
    Token("--accent-error", "Ошибка", "Акценты", "color"),
    Token("--accent-error-darker", "Ошибка, тёмнее", "Акценты", "color"),
    Token("--term-fg", "Терминал: текст", "Терминал", "color"),
    Token("--term-dim", "Терминал: тусклый", "Терминал", "color"),
    Token("--term-ok", "Терминал: успех", "Терминал", "color"),
    Token("--term-warn", "Терминал: предупреждение", "Терминал", "color"),
    Token("--term-error", "Терминал: ошибка", "Терминал", "color"),
    Token("--term-info", "Терминал: сведения", "Терминал", "color"),
    Token("--font-main", "Основной шрифт", "Шрифты", "font"),
    Token("--font-console", "Шрифт терминала", "Шрифты", "font"),
    Token("--fs-console", "Размер шрифта терминала", "Шрифты", "length"),
    Token("--radius", "Скругление углов", "Форма", "length"),
    Token("--border-w", "Толщина рамок", "Форма", "length"),
    Token("--tab-h", "Высота заголовка окна", "Форма", "length"),
    Token("--cell", "Шаг сетки рабочего стола", "Форма", "length"),
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
