"""Картинка и узор рабочего стола ОС: значения, проверка и вывод слоёв.

Хранится в SystemType.wallpaper одним словарём и не зависит от стиля. Картинка это файл из Nextcloud (id файла), её отдаёт
desktop.views.wallpaper без проверки ключей: автор выбрал её для ОС сам. Узор рисуется плиткой из SVG без файлов.
Цвет под ними это токен «Фон рабочего стола» (--bg).
"""
import re
from mimetypes import guess_type
from urllib.parse import quote

from django.utils.html import format_html
from django.utils.safestring import mark_safe

MODES = {"center": "По центру", "cover": "Растянуть"}
PATTERNS = {"none": "Нет", "grid": "Сетка", "dots": "Точки", "plus": "Плюсики"}
SIZE_MIN, SIZE_MAX = 8, 200

DEFAULT = {"file_id": "", "file_name": "", "mode": "center", "opacity": 100, "pattern": "none", "pattern_color": "#ffffff", "pattern_size": 24, "pattern_opacity": 15}
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_FILE_ID = re.compile(r"^[\w.-]{1,64}$")


def clean(data):
    """Полный словарь настроек: недостающее берётся по умолчанию, лишние ключи отбрасываются."""
    data = data if isinstance(data, dict) else {}
    return {name: data.get(name, default) for name, default in DEFAULT.items()}


def problems(data):
    """Ошибки значений: список строк."""
    data = clean(data)
    found = []
    file_id = data["file_id"]
    if file_id != "" and not (isinstance(file_id, str) and _FILE_ID.match(file_id)):
        found.append("Файл картинки выбирается из хранилища.")
    if data["mode"] not in MODES:
        found.append(f"Режим картинки: {', '.join(MODES)}.")
    if data["pattern"] not in PATTERNS:
        found.append(f"Узор: {', '.join(PATTERNS)}.")
    if not (isinstance(data["pattern_color"], str) and _COLOR.match(data["pattern_color"])):
        found.append("Цвет узора пишется как #1a2b3c.")
    for name, label, low, high in (("opacity", "Прозрачность картинки", 0, 100), ("pattern_opacity", "Прозрачность узора", 0, 100),
                                   ("pattern_size", "Шаг узора", SIZE_MIN, SIZE_MAX)):
        value = data[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            found.append(f"{label}: целое число от {low} до {high}.")
    return found


def is_image_name(name):
    return (guess_type(name or "")[0] or "").startswith("image/")


def stored_file_name(file_id):
    """Имя файла в хранилище; ValidationError, если файла нет, это папка или не картинка."""
    from django.core.exceptions import ValidationError

    from assets.nextcloud import NextcloudClient

    try:
        file = NextcloudClient.from_settings().get_file_by_id(file_id)
    except Exception:
        raise ValidationError({"wallpaper": ["Хранилище не отвечает."]})
    if file is None or file.is_directory:
        raise ValidationError({"wallpaper": ["Такого файла нет в хранилище."]})
    if not is_image_name(file.filename):
        raise ValidationError({"wallpaper": ["Нужна картинка (png, jpg, svg, webp)."]})
    return file.filename


def is_empty(data):
    data = clean(data)
    return not data["file_id"] and data["pattern"] == "none"


def tile(pattern, color, size):
    """Плитка узора как адрес data:image/svg+xml (цвет уже проверен как #rrggbb)."""
    c, s = color, size
    mid = s / 2
    shapes = {
        "grid": f'<path d="M0 .5H{s}M.5 0V{s}" stroke="{c}" stroke-width="1" fill="none"/>',
        "dots": f'<circle cx="{mid}" cy="{mid}" r="1.4" fill="{c}"/>',
        "plus": f'<path d="M{mid - 4} {mid}H{mid + 4}M{mid} {mid - 4}V{mid + 4}" stroke="{c}" stroke-width="1" fill="none"/>',
    }
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}">{shapes[pattern]}</svg>'
    return "data:image/svg+xml," + quote(svg, safe="")


def render(url, data):
    """HTML слоёв (стиль и два элемента) или пустая строка; url это адрес картинки с версией.
    Слои лежат внутри #desktop: над его собственным фоном стиля, под значками и окнами."""
    data = clean(data)
    if problems(data) or is_empty(data):
        return ""
    rules, blocks = ["#desktop{isolation:isolate}#os-wallpaper,#os-pattern{position:absolute;inset:0;z-index:-1;pointer-events:none}"], []
    if data["file_id"]:
        fit = "scale-down" if data["mode"] == "center" else "cover"
        rules.append(f"#os-wallpaper{{opacity:{data['opacity'] / 100:g}}}#os-wallpaper img{{display:block;width:100%;height:100%;object-fit:{fit}}}")
        blocks.append(format_html('<div id="os-wallpaper" aria-hidden="true"><img src="{}" alt=""></div>', url))
    if data["pattern"] != "none":
        size = data["pattern_size"]
        rules.append(f'#os-pattern{{opacity:{data["pattern_opacity"] / 100:g};background:url("{tile(data["pattern"], data["pattern_color"], size)}") 0 0/{size}px {size}px}}')
        blocks.append(mark_safe('<div id="os-pattern" aria-hidden="true"></div>'))
    return mark_safe(f'<style id="os-wallpaper-style">{"".join(rules)}</style>') + mark_safe("".join(str(b) for b in blocks))
