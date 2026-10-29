"""Виджет карты: разбор строк, маркеры, подписи, области и сцена."""
from html import escape
import re

from django.urls import NoReverseMatch, reverse

from map.icons import icon_name
from map.scenes import internal_url
from documents.widgets.base import IMAGE_RATIOS, MAP_MODES, _choice, _head_args, _lines, _num, widget
from documents.widgets.media import _asset_figure, _asset_missing


MARK_COLORS = ("red", "blue", "green", "orange", "purple", "yellow", "teal", "grey")


MARK_ALIASES = {
    "красный": "red", "синий": "blue", "зелёный": "green", "зеленый": "green", "оранжевый": "orange",
    "фиолетовый": "purple", "жёлтый": "yellow", "желтый": "yellow", "бирюзовый": "teal",
    "серый": "grey", "gray": "grey", "black": "grey", "чёрный": "grey", "черный": "grey",
}


_MARKER = re.compile(
    r"^(.*?)\s*\|\s*(-?\d+(?:[.,]\d+)?)[\s,;]+(-?\d+(?:[.,]\d+)?)(?:\s+([^\W\d_]+))?(?:\s+([^\W\d_]+))?\s*$"
)


# выноска: «note ТЕКСТ | lat lon [+dx -dy] [цвет] [-> адрес]»; \n в тексте переносит строку
_CALLOUT = re.compile(
    r"^(?:note|выноска)\s+(.+?)\s*\|\s*(-?\d+(?:[.,]\d+)?)[\s,;]+(-?\d+(?:[.,]\d+)?)"
    r"(?:\s+([+-]\d+)\s+([+-]\d+))?(?:\s+([^\W\d_]+))?\s*$",
    re.IGNORECASE,
)


DEFAULT_CALLOUT_OFFSET = (70, -50)


def mark_color(word):
    """Имя цвета из разметки (red, синий...) -> имя из MARK_COLORS или '' (неизвестное и пустое)."""
    word = (word or "").strip().lower()
    word = MARK_ALIASES.get(word, word)
    return word if word in MARK_COLORS else ""


def split_highlight_token(token):
    """«POL:blue» -> («POL», 'blue'); цвет неизвестен -> ('POL', ''), доступно и «-POL-3» без цвета."""
    base, _, word = token.rpartition(":")
    if not base:
        return token, ""
    return base, mark_color(word)


MAX_MARKERS = 12


TEXT_LIMIT_CALLOUT = 200


MAX_REGIONS = 24


AUTO_COLORS = ("red", "blue", "green", "orange", "purple", "teal", "yellow", "grey")


_EXCEPT = re.compile(r"^(?:except|кроме)\s+(.+)$", re.IGNORECASE)


def parse_map_line(line):
    """Строка тела ::map -> ('marker', название, lat, lon, цвет, неизвестное слово, ссылка, значок) |
    ('callout', текст, lat, lon, (dx, dy), цвет, неизвестное слово, ссылка) |
    ('region', [(токен, цвет)], ссылка) | ('except', [токен]) | None для пустой строки.

        Краков | 50.06 19.94 red      метка
        POL blue, DEU orange          выделение (через запятую; цвет последним словом)
        Краков | 50 19 -> Technologies/Report   ссылка по клику: «-> адрес» в конце строки
        note Склад | 50 19 +80 -40 blue  выноска: плашка с текстом и линией к месту (смещение в
                                      пикселях необязательно, \\n переносит строку; «выноска» то же, что note)
        Склад | 50 19 red star        цвет и значок (булавка, крест, кольцо, точка, квадрат, треугольник,
                                      ромб, звезда, флажок, восклицание, вопрос, прицел, галочка)
        except CZE-3  /  -CZE-3       исключить провинцию из выделенного
    """
    line = line.strip()
    if not line:
        return None

    # «-> адрес» в конце строки: клик по метке или выделению открывает ссылку
    link = ""
    match = re.search(r"\s+->\s+(\S.*)$", line)
    if match:
        line, link = line[: match.start()].strip(), match.group(1).strip()

    callout = _CALLOUT.match(line)
    if callout:
        lat, lon = float(callout.group(2).replace(",", ".")), float(callout.group(3).replace(",", "."))
        offset = (
            (int(callout.group(4)), int(callout.group(5))) if callout.group(4) else DEFAULT_CALLOUT_OFFSET
        )
        word = callout.group(6)
        return ("callout", re.sub(r"[ \t]*\\n[ \t]*", "\n", callout.group(1)).strip(), lat, lon, offset,
                mark_color(word), word if word and not mark_color(word) else "", link)

    marker = _MARKER.match(line)
    if marker:
        lat, lon = float(marker.group(2).replace(",", ".")), float(marker.group(3).replace(",", "."))
        # после координат до двух слов в любом порядке: цвет и значок (red star, звезда красный).
        # Неизвестное слово не теряет метку: она рисуется по умолчанию, линтер ругается
        color = icon = bad = ""
        for word in (marker.group(4), marker.group(5)):
            if not word:
                continue
            if mark_color(word) and not color:
                color = mark_color(word)
            elif icon_name(word) and not icon:
                icon = icon_name(word)
            elif not bad:
                bad = word
        return ("marker", marker.group(1).strip(), lat, lon, color, bad, link, icon)

    exclusion = _EXCEPT.match(line)
    if exclusion:
        return ("except", [t for t in re.split(r"[\s,;]+", exclusion.group(1)) if t])
    if line.startswith("-") and len(line) > 1:
        return ("except", [t for t in re.split(r"[\s,;]+", line[1:]) if t])

    items = []
    for part in line.split(","):
        words = part.split()
        if not words:
            continue
        color = mark_color(words[-1]) if len(words) > 1 else ""
        token = " ".join(words[:-1] if color else words)
        items.append((token, color))
    return ("region", items, link)


def _marker_rows(text):
    """Метки тела блока: [(название, lat, lon, цвет, ссылка, значок)]; координаты вне карты пропускаются."""
    rows = []
    for line in _lines(text):
        parsed = parse_map_line(line)
        if parsed and parsed[0] == "marker" and -85 <= parsed[2] <= 85 and -180 <= parsed[3] <= 180:
            rows.append((parsed[1], parsed[2], parsed[3], parsed[4], parsed[6], parsed[7]))
    return rows[:MAX_MARKERS]


def _callout_rows(text):
    """Выноски тела блока: [{lat, lon, offset, color, url, text}]; координаты вне карты пропускаются."""
    rows = []
    for line in _lines(text):
        parsed = parse_map_line(line)
        if parsed and parsed[0] == "callout" and -85 <= parsed[2] <= 85 and -180 <= parsed[3] <= 180:
            rows.append({
                "lat": parsed[2], "lon": parsed[3], "offset": list(parsed[4]), "color": parsed[5],
                "url": internal_url(parsed[7]), "text": parsed[1][:TEXT_LIMIT_CALLOUT],
            })
    return rows[:MAX_MARKERS]


def _highlight_items(head, text):
    """Что выделять: [(токен, цвет, ссылка)]. Токены из заголовка (старая запись
    highlight="POL:blue -CZE-3") идут первыми, затем строки тела. Исключения: токены «-КОД»."""
    items = []
    for token in re.split(r"[\s,;]+", head.get("highlight") or head.get("regions") or ""):
        if token:
            items.append((*split_highlight_token(token), ""))
    for line in _lines(text):
        parsed = parse_map_line(line)
        if not parsed:
            continue
        if parsed[0] == "region":
            items.extend((token, color, parsed[2]) for token, color in parsed[1])
        elif parsed[0] == "except":
            items.extend(("-" + token.lstrip("-"), "", "") for token in parsed[1])
    return items[:MAX_REGIONS]


def _scale_text(zoom, lat):
    """Подпись масштаба для начального вида: километров в 100 пикселях."""
    import math

    km = 78271.52 * math.cos(math.radians(lat)) / (2 ** float(zoom)) * 100 / 1000
    return f"{km:.0f}" if km >= 10 else f"{km:.1f}"


@widget("map", raw=True)
def map_widget(text, ctx, args=""):
    """Карта мира с выделением провинций и метками.

    ::map date=2041-03-12 caption="Порт на тот день"
    POL blue
    CZE green, SVK
    except CZE-3
    Порт | 48.8 2.3 red
    Склад | 48.9 2.4
    ::

    Заголовок только про саму карту: date (ГГГГ-ММ-ДД), caption, lat, lon, zoom (0-18),
    mode (political: границы, заливка, названия; physical: только рельеф), labels=off
    (без названий провинций), ratio, width. Без lat и lon вид подбирается по выделенному и меткам.

    Тело блока, по строке:
      КОД [цвет]             выделение: провинция (RUS-32), страна (POL, POL-2013 или название;
                             страна берётся по владениям на date); несколько через запятую;
                             цвет последним словом, без цвета разные выделения красятся по очереди
      except КОД  или  -КОД  убрать провинцию (или страну) из выделенного
      Название | lat lon [цвет]   метка

    Старая запись highlight="POL:blue -CZE-3" в заголовке по-прежнему работает.

    У web, rec и инфобокса карта живая (можно двигать и приближать), у doc и scan неподвижный
    кадр. Вид выбирает wiki.js по классу страницы, поэтому в разметке два адреса.
    """
    from urllib.parse import quote, quote_plus

    from datetime import date as _date

    from map.bounds import resolve_highlight, union, view_for

    import json

    from map.models import MapScene
    from map.scenes import visible_features
    from secure.access import satisfied

    head = _head_args(args)
    markers = _marker_rows(text)
    callouts = _callout_rows(text)

    # сохранённая карта: камера, дата и режим берутся из неё, если заголовок не задал свои
    scene = None
    scene_payload = None
    if head.get("scene"):
        scene = MapScene.objects.filter(slug=head["scene"].strip()).first()
        if scene is None:
            return _asset_missing(head["scene"], "MAP NOT FOUND")
        if not satisfied(scene.key_condition, ctx.keys):
            return _asset_missing(head["scene"], "MAP RESTRICTED")
        if scene.base_date and not head.get("date"):
            head["date"] = scene.base_date.isoformat()
        if not head.get("mode"):
            head["mode"] = scene.mode
        if head.get("lat") in (None, "") and head.get("lon") in (None, ""):
            head["lat"], head["lon"] = f"{scene.lat:g}", f"{scene.lon:g}"
            if not head.get("zoom"):
                head["zoom"] = f"{scene.zoom:g}"
        if not head.get("caption") and not head.get("title"):
            head["caption"] = scene.title
    raw_date = (head.get("date") or "").strip()
    try:
        on_date = _date.fromisoformat(raw_date)
    except ValueError:
        on_date = None
    split = _highlight_items(head, text)
    groups, _unknown = resolve_highlight([base for base, _c, _u in split], on_date) if split else ([], [])
    colors = {base.upper(): color for base, color, _u in split if color}
    links = {base.upper(): url for base, _c, url in split if url}
    for group in groups:
        group["color"] = colors.get(group["token"].upper(), colors.get(group["name"].upper(), ""))
        group["url"] = internal_url(links.get(group["token"].upper(), links.get(group["name"].upper(), "")))
    # без цвета выделения красятся по очереди разными цветами (одно выделение остаётся цвета темы)
    plain = [g for g in groups if not g["color"]]
    if len(plain) > 1:
        free = [c for c in AUTO_COLORS if c not in {g["color"] for g in groups}]
        for index, group in enumerate(plain):
            group["color"] = free[index % len(free)] if free else AUTO_COLORS[index % len(AUTO_COLORS)]
    # провинция в нескольких токенах (POL:blue и POL-2:red) берёт цвет последнего
    chosen = {}
    for group in groups:
        for code in group["codes"]:
            chosen[code] = (group["color"], group["url"])
    region_codes = [
        code + ((":" + color + (":" + quote_plus(url) if url else "")) if color or url else "")
        for code, (color, url) in chosen.items()
    ]

    has_view = head.get("lat") not in (None, "") and head.get("lon") not in (None, "")
    if has_view:
        lat = float(_num(head.get("lat"), 20, -85, 85))
        lon = float(_num(head.get("lon"), 10, -180, 180))
        zoom = float(_num(head.get("zoom"), 4, 0, 18))
    else:
        box = union([b for g in groups for b in g["boxes"]] + [[lo, la, lo, la] for _, la, lo, _c, _u, _i in markers]
        + [[c["lon"], c["lat"], c["lon"], c["lat"]] for c in callouts])
        if box is not None:
            lat, lon, zoom = view_for(box)
            if head.get("zoom"):
                zoom = float(_num(head.get("zoom"), zoom, 0, 18))
        else:
            lat, lon, zoom = 20.0, 10.0, 2.0

    query = "embed=1"
    mode = _choice(head.get("mode"), MAP_MODES, "")
    if mode:
        query += f"&mode={mode}"
    date = (head.get("date") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        date = ""
    if date:
        query += f"&date={date}"
    if (head.get("labels") or "").strip().lower() in ("off", "0", "no", "нет"):
        query += "&labels=0"
    if region_codes:
        query += "&regions=" + ",".join(region_codes)
    for label, la, lo, color, link, icon in markers:
        query += f"&m={la},{lo},{color},{icon},{quote_plus(internal_url(link))},{quote_plus(label)}"
    for callout in callouts:
        query += "&c=" + quote(json.dumps(callout, ensure_ascii=False, separators=(",", ":")), safe="")
    if scene is not None:
        if scene.bounds:
            query += "&bounds=" + ",".join(f"{v:g}" for v in scene.bounds)
        if scene.min_zoom is not None:
            query += f"&minzoom={scene.min_zoom:g}"
        if scene.max_zoom is not None:
            query += f"&maxzoom={scene.max_zoom:g}"
        flat = (head.get("flat") or "").strip().lower()
        if flat in ("on", "1", "yes", "да") or (not flat and scene.flat):
            query += "&flat=1"
        scene_payload = _scene_payload(scene, ctx.keys, on_date)
    elif (head.get("flat") or "").strip().lower() in ("on", "1", "yes", "да"):
        query += "&flat=1"

    try:
        base = reverse("map:index")
    except NoReverseMatch:
        return _asset_missing(head.get("caption", ""), "MAP NOT AVAILABLE")
    view = f"#{zoom:g}/{lat:g}/{lon:g}"
    live = f"{base}?{query}{view}"
    still = f"{base}?{query}&static=1{view}"
    ratio = IMAGE_RATIOS.get((head.get("ratio") or "").strip(), "16-9")

    stamp = f'<span class="map-stamp"><span class="map-stamp-name">КАРТА</span>'
    if date:
        stamp += f'<span class="map-stamp-date">{escape(date)}</span>'
    stamp += "</span>"
    north = (
        '<svg class="map-north" viewBox="0 0 24 32" aria-hidden="true">'
        '<path class="map-north-arrow" d="M12 1 L20 29 L12 23 L4 29 Z"/>'
        '<text x="12" y="17" text-anchor="middle" class="map-north-n">N</text></svg>'
    )
    scale = (
        '<div class="map-scale"><span class="map-scale-bar"></span>'
        f'<span class="map-scale-text" data-km="{_scale_text(zoom, lat)}">{_scale_text(zoom, lat)} км</span></div>'
    )
    inner = (
        f'<div class="image-frame"><div class="map-frame image-ratio-{ratio}">'
        f'<iframe class="map-embed" title="Карта" loading="lazy" '
        f'data-live="{escape(live, quote=True)}" data-static="{escape(still, quote=True)}"></iframe>'
        f'<div class="map-ui" aria-hidden="true">{stamp}{north}{scale}</div>'
        "</div>"
        f'<div class="map-status" data-lat="{lat:g}" data-lon="{lon:g}" data-zoom="{zoom:g}">'
        f'{_coord(lat, "N", "S")} {_coord(lon, "E", "W")} · ×{zoom:g}</div>'
        "</div>"
    )

    legend = []
    for index, (label, la, lo, color, _link, _icon) in enumerate(markers, 1):
        legend.append(
            f'<li class="map-legend-marker"{_color_attr(color)}><b>{index}</b>{ctx.inline(label)}</li>'
        )
    for group in groups:
        legend.append(
            f'<li class="map-legend-region"{_color_attr(group["color"])}><i></i>{escape(group["name"])}'
            f'<span>{escape(group["token"])}</span></li>'
        )
    legend_html = f'<ol class="map-legend">{"".join(legend)}</ol>' if legend else ""

    figure = _asset_figure("map", inner, {**head, "width": head.get("width", "100")}, ctx)
    if scene_payload is not None:
        figure = figure.replace(
            "<figure ", f'<figure data-scene="{escape(json.dumps(scene_payload, ensure_ascii=False), quote=True)}" ', 1
        )
    figure = figure.replace("</figure>", f"{legend_html}</figure>", 1) if legend_html else figure
    # подпись и рамка у карты те же, что у картинки документа
    return figure.replace("widget widget--map", "widget widget--map widget--image", 1)


def _scene_payload(scene, keys, on_date):
    from map.scenes import scene_payload

    return scene_payload(scene, keys, on_date)


def _color_attr(color):
    return f' data-color="{color}"' if color else ""


def _coord(value, plus, minus):
    return f"{abs(value):.2f}°{plus if value >= 0 else minus}"
