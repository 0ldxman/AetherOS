"""Иконки приложений рабочего стола.

Приложение (файл .app) называет иконку по имени из каталога ниже, а картинку берёт стиль ОС машины: у каждого стиля свой набор
(static/ui/icons/<стиль>/<имя>.svg, собирается tools/build_icon_packs.py). Стиль tui рисует текстовый значок из каталога, glitched
берёт набор aether. Нет файла в наборе стиля: берётся набор aether, нет и его: текстовый значок.
"""
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static

DEFAULT_PACK = "aether"
TEXT_ONLY = {"tui"}                             # стили без картинок: значок из текста
PACK_OF = {"glitched": "aether"}                # стиль без своего набора берёт чужой

# имя, подпись, текстовый значок (до 8 знаков: для стиля tui и списков, где картинке нет места)
CATALOG = (
    ("terminal", "Терминал", ">_"), ("mail", "Почта", "@"), ("book", "Книга, вики", "W"), ("map", "Карта", "M"),
    ("folder", "Папка", "[]"), ("file", "Файл", "▤"), ("image", "Картинка", "▣"), ("audio", "Аудио", "♪"), ("video", "Видео", "▶"),
    ("archive", "Архив", "▦"), ("key", "Ключ", "K"), ("lock", "Замок", "#"), ("settings", "Настройки", "*"), ("network", "Сеть", "~"),
    ("database", "База данных", "DB"), ("chat", "Чат", "\""), ("monitor", "Монитор", "[=]"), ("shield", "Защита", "S"),
    ("search", "Поиск", "?"), ("tools", "Инструменты", "T"), ("globe", "Глобус", "O"), ("camera", "Камера", "C"),
    ("calendar", "Календарь", "D"), ("user", "Учётная запись", "U"), ("radio", "Связь", "R"), ("chart", "График", "/"), ("app", "Приложение", "A"),
)
NAMES = tuple(name for name, _, _ in CATALOG)
ASCII = {name: text for name, _, text in CATALOG}
GENERIC = "app"


def pack_of(style):
    return PACK_OF.get(style, style)


@lru_cache(maxsize=None)
def _has(pack, name):
    return (Path(settings.BASE_DIR) / "static" / "ui" / "icons" / pack / f"{name}.svg").is_file()


def icon_url(style, name):
    """Адрес картинки иконки в стиле или пустая строка (тогда рисуется текстовый значок)."""
    if style in TEXT_ONLY or name not in ASCII:
        return ""
    for pack in (pack_of(style), DEFAULT_PACK):
        if _has(pack, name):
            return static(f"ui/icons/{pack}/{name}.svg")
    return ""


def glyph(name):
    return ASCII.get(name, ASCII[GENERIC])
