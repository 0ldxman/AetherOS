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


def resolve_regions(codes):
    """Коды провинций из БД -> [(код, source_code, название, рамка или None)] и список неизвестных кодов."""
    from .models import Province

    wanted = [c.strip().upper() for c in codes if c.strip()]
    # регистр кода в БД не гарантирован, поэтому сравниваем без регистра
    found = {}
    for province in Province.objects.all().only("code", "source_code", "name"):
        if province.code.upper() in wanted:
            found[province.code.upper()] = province

    bounds = _bounds()
    rows, unknown = [], []
    for code in wanted:
        province = found.get(code)
        if province is None:
            unknown.append(code)
            continue
        rows.append((province.code, province.source_code, province.name, bounds.get(province.source_code)))
    return rows, unknown


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
