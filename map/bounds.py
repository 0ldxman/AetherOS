"""Рамки и названия провинций для виджета ::map: по коду из БД (RUS-32) найти место на карте."""
import json
from functools import lru_cache
from pathlib import Path

BOUNDS_FILE = Path(__file__).resolve().parent / "data" / "province_bounds.json"


@lru_cache(maxsize=1)
def _bounds():
    try:
        return json.loads(BOUNDS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


MAX_PROVINCES = 600


def _owned_by(country_ids, on_date):
    """source_code провинций, которыми на дату (без даты: сейчас) владеет любая из стран."""
    from .models import Ownership

    qs = Ownership.objects.all()
    if on_date is not None:
        qs = qs.filter(date_from__lte=on_date)
    latest = {}
    for province_id, country_id, source_code in qs.order_by("province_id", "-date_from", "-id").values_list(
        "province_id", "country_id", "province__source_code"
    ):
        latest.setdefault(province_id, (country_id, source_code))
    return [source for country_id, source in latest.values() if country_id in country_ids]


def resolve_highlight(tokens, on_date=None):
    """Что выделить: коды провинций (RUS-32), страны (POL, POL-2013 или название) и исключения (-POL-3).

    -> (группы, неизвестные токены). Группа: словарь kind (province|country), token, name,
    codes (source_code провинций) и boxes (их рамки).
    """
    from .models import Country, Province

    wanted = [t.strip() for t in tokens if t.strip()]
    provinces = {p.code.upper(): p for p in Province.objects.all().only("code", "source_code", "name")}
    countries = list(Country.objects.all().only("id", "code", "name"))
    bounds = _bounds()

    groups, unknown, excluded = [], [], set()
    for token in wanted:
        if token.startswith("-"):
            province = provinces.get(token[1:].upper())
            if province is None:
                unknown.append(token)
            else:
                excluded.add(province.source_code)
            continue

        province = provinces.get(token.upper())
        if province is not None:
            groups.append({
                "kind": "province", "token": province.code, "name": province.name,
                "codes": [province.source_code],
            })
            continue

        key = token.upper()
        ids = {
            c.id for c in countries
            if c.code.upper() == key or c.code.upper().startswith(key + "-") or c.name.upper() == key
        }
        if not ids:
            unknown.append(token)
            continue
        name = next((c.name for c in countries if c.id in ids), token)
        groups.append({"kind": "country", "token": token.upper(), "name": name, "codes": _owned_by(ids, on_date)})

    total = 0
    for group in groups:
        group["codes"] = [c for c in group["codes"] if c not in excluded][: max(0, MAX_PROVINCES - total)]
        total += len(group["codes"])
        group["boxes"] = [bounds.get(c) for c in group["codes"]]
    return groups, unknown


def union(boxes):
    """Общая рамка нескольких [запад, юг, восток, север] или None."""
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def view_for(box, width_px=800, height_px=450, pad=1.25):
    """Центр и зум, в которые рамка помещается в кадр (меркатор, плитки 512 px)."""
    import math

    west, south, east, north = box
    lon = (west + east) / 2
    lat = (south + north) / 2
    span_lon = max((east - west) * pad, 0.02)

    def merc(y):
        return math.log(math.tan(math.pi / 4 + math.radians(max(-85, min(85, y))) / 2))

    span_merc = max(abs(merc(north) - merc(south)) * pad, 1e-4)
    zoom_x = math.log2(width_px / 512 * 360 / span_lon)
    zoom_y = math.log2(height_px / 512 * 2 * math.pi / span_merc)
    return round(lat, 3), round(lon, 3), round(max(0.5, min(12, min(zoom_x, zoom_y))), 1)
