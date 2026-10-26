"""Сохранённые карты (сцены): проверка пометок, ссылки и выбор того, что видит игрок.

Сцена это ссылка на базовую карту (дата мира) плюс список пометок. Пометка словарь:

    marker   coords [lon, lat]                      label, color, icon, url, key
    line     coords [[lon, lat], ...] (от 2)        label, color, width, dash, smooth, url, key
             (smooth: линия, нарисованная от руки, без вершин для правки)
    arrow    как line, на конце наконечник
    polygon  coords [[lon, lat], ...] (от 3)        label, color, fill, url, key
    circle   coords [lon, lat], radius_km           label, color, fill, url, key
    text     coords [lon, lat], text                color, size, key
    callout  coords [lon, lat] (место), text        color, offset [dx, dy] в пикселях, url, key
             выноска: плашка с текстом, от неё линия к месту
    region   token (POL, RUS-32)            label, color, fill, url, key

from, to  необязательные даты (ГГГГ-ММ-ДД): пометка видна только на дату сцены внутри этого промежутка.

color это имя из палитры (red, blue...), url внутренний адрес, key условие по ключам
(то же, что у спойлеров), оно проверяется на сервере и закрытые пометки в страницу не попадают.
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, get_script_prefix, reverse

from secure.access import satisfied, validate_requirements

from .icons import ICON_NAMES
from wiki.markup.expr import SpoilerSyntaxError, parse_expr

FEATURE_TYPES = ("marker", "line", "arrow", "polygon", "circle", "text", "callout", "region")
COLORS = ("red", "blue", "green", "orange", "purple", "yellow", "teal", "grey")
MAX_FEATURES = 400
MAX_POINTS = 500
TEXT_LIMIT = 200


def internal_url(raw):
    """Ссылка пометки -> внутренний адрес сайта или '' для пустой/небезопасной.

    «/wiki/…» берётся как есть (с префиксом сайта), всё остальное считается путём в вики
    (Technologies/First report). Адреса с другим сайтом, схемой и «\\» не принимаются.
    """
    raw = (raw or "").strip()
    if not raw or "\\" in raw or "://" in raw or raw.startswith("//") or ":" in raw.split("/")[0]:
        return ""
    prefix = get_script_prefix().rstrip("/")
    if raw.startswith("/"):
        return raw if prefix and raw.startswith(prefix + "/") else prefix + raw
    try:
        return reverse("wiki:resolve", kwargs={"path": raw.strip("/")})
    except NoReverseMatch:
        return ""


def _point(value, where):
    try:
        lon, lat = float(value[0]), float(value[1])
    except (TypeError, ValueError, IndexError):
        raise ValidationError(f"{where}: точка это [долгота, широта].")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValidationError(f"{where}: точка вне карты.")
    return [round(lon, 5), round(lat, 5)]


def clean_features(raw):
    """Проверка и нормализация списка пометок; кривое -> ValidationError с номером пометки."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValidationError("Пометки это список.")
    if len(raw) > MAX_FEATURES:
        raise ValidationError(f"Слишком много пометок (не больше {MAX_FEATURES}).")

    result = []
    for number, item in enumerate(raw, 1):
        where = f"Пометка {number}"
        if not isinstance(item, dict) or item.get("type") not in FEATURE_TYPES:
            raise ValidationError(f"{where}: тип один из {', '.join(FEATURE_TYPES)}.")
        kind = item["type"]
        clean = {"type": kind}

        if kind in ("marker", "circle", "text", "callout"):
            clean["coords"] = _point(item.get("coords"), where)
        elif kind in ("line", "arrow", "polygon"):
            points = item.get("coords")
            need = 3 if kind == "polygon" else 2
            if not isinstance(points, list) or not need <= len(points) <= MAX_POINTS:
                raise ValidationError(f"{where}: нужно от {need} точек.")
            clean["coords"] = [_point(p, where) for p in points]
        else:
            token = str(item.get("token") or "").strip()
            if not token or token.startswith("-"):
                raise ValidationError(f"{where}: у выделения нужен token без минуса (POL, RUS-32).")
            clean["token"] = token[:64]

        if kind == "circle":
            try:
                radius = float(item.get("radius_km"))
            except (TypeError, ValueError):
                raise ValidationError(f"{where}: у круга нужен radius_km.")
            if not 0 < radius <= 20000:
                raise ValidationError(f"{where}: radius_km от 0 до 20000.")
            clean["radius_km"] = radius
        if kind in ("text", "callout"):
            text = str(item.get("text") or "").strip()[:TEXT_LIMIT]
            if not text:
                raise ValidationError(f"{where}: у текста и выноски нужен text.")
            clean["text"] = text
        if kind == "callout":
            try:
                dx, dy = (float(v) for v in (item.get("offset") or [70, -50]))
            except (TypeError, ValueError):
                raise ValidationError(f"{where}: offset это [dx, dy] в пикселях.")
            clean["offset"] = [max(-500, min(500, round(dx))), max(-500, min(500, round(dy)))]

        color = item.get("color")
        if color:
            if color not in COLORS:
                raise ValidationError(f"{where}: цвет один из {', '.join(COLORS)}.")
            clean["color"] = color
        if kind == "marker" and item.get("icon"):
            if item["icon"] not in ICON_NAMES:
                raise ValidationError(f"{where}: значок один из {', '.join(ICON_NAMES)}.")
            clean["icon"] = item["icon"]
        if item.get("label") and kind not in ("text", "callout"):
            clean["label"] = str(item["label"]).strip()[:TEXT_LIMIT]
        if item.get("url"):
            clean["url"] = str(item["url"]).strip()[:300]
        if kind in ("line", "arrow"):
            if item.get("width"):
                clean["width"] = max(1, min(8, float(item["width"])))
            if item.get("dash"):
                clean["dash"] = True
            if item.get("smooth"):
                clean["smooth"] = True
        if kind in ("polygon", "circle", "region") and "fill" in item:
            clean["fill"] = bool(item["fill"])
        if kind == "text" and item.get("size"):
            clean["size"] = max(8, min(48, float(item["size"])))
        # видимость по времени: на дату сцены между from и to (границы необязательны)
        span = {}
        for name in ("from", "to"):
            if item.get(name):
                try:
                    span[name] = date.fromisoformat(str(item[name])).isoformat()
                except ValueError:
                    raise ValidationError(f"{where}: дата «{name}» вида ГГГГ-ММ-ДД.")
        if span.get("from") and span.get("to") and span["from"] > span["to"]:
            raise ValidationError(f"{where}: «from» позже «to».")
        clean.update(span)

        key = item.get("key")
        if isinstance(key, str):
            # условие строкой, как у спойлеров: secret and not other
            try:
                key = parse_expr(key) if key.strip() else None
            except SpoilerSyntaxError as error:
                raise ValidationError(f"{where}: условие по ключам: {error}")
        if key:
            validate_requirements(key)
            clean["key"] = key
        result.append(clean)
    return result


def in_span(item, on_date):
    """Видна ли пометка на дату: без даты сцены или без границ видна всегда."""
    if on_date is None:
        return True
    iso = on_date.isoformat()
    return (not item.get("from") or item["from"] <= iso) and (not item.get("to") or iso <= item["to"])


def visible_features(features, keys, on_date=None):
    """Пометки, которые видны игроку с этими ключами на дату (поле key уже проверено и наружу не уходит)."""
    shown = []
    for item in features or []:
        if satisfied(item.get("key"), keys) and in_span(item, on_date):
            shown.append({k: v for k, v in item.items() if k not in ("key", "from", "to")})
    return shown


def scene_payload(scene, keys, on_date):
    """Пометки сцены для страницы: видимые игроку на дату, ссылки внутренние, выделения раскрыты в провинции."""
    from .bounds import resolve_highlight

    payload = []
    for item in visible_features(scene.features, keys, on_date):
        item = dict(item)
        if item.get("url"):
            item["url"] = internal_url(item["url"])
            if not item["url"]:
                del item["url"]
        if item["type"] == "region":
            groups, _unknown = resolve_highlight([item["token"]], on_date)
            codes = [code for g in groups for code in g["codes"]]
            if not codes:
                continue
            item = {**{k: v for k, v in item.items() if k != "token"}, "type": "regions", "codes": codes}
        payload.append(item)
    return payload
