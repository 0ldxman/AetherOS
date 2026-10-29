"""Внешняя граница набора провинций: страна как одно целое, без внутренних границ между её провинциями.

Каждая граница между двумя соседними провинциями входит в контуры обеих, поэтому при склейке такой отрезок
встречается дважды и сокращается; остаются отрезки, у которых соседа среди выбранных нет. Из них собираются
цепочки (внешние границы и границы дыр). Данные Natural Earth топологичны: общие отрезки совпадают по координатам.
"""
import hashlib
import math
from collections import defaultdict

from django.core.cache import cache

SCALE = 100000          # координаты сравниваются с точностью до 1e-5 градуса (около метра)
TOLERANCE = 0.001       # упрощение линии, градусы (около 100 м): незаметно на масштабе страны
CACHE_SECONDS = 24 * 3600


def _chains(edges):
    """Отрезки (пары точек) -> список цепочек точек. Замкнутые кольца возвращаются с повтором первой точки."""
    neighbours = defaultdict(list)
    for a, b in edges:
        neighbours[a].append(b)
        neighbours[b].append(a)

    used = set()
    chains = []

    def walk(start, nxt):
        chain = [start]
        previous, current = start, nxt
        while True:
            used.add((previous, current) if previous < current else (current, previous))
            chain.append(current)
            options = [p for p in neighbours[current] if (min(current, p), max(current, p)) not in used]
            if not options:
                return chain
            previous, current = current, options[0]
            if current == start:
                used.add((chain[-1], current) if chain[-1] < current else (current, chain[-1]))
                chain.append(current)
                return chain

    # сначала цепочки, начинающиеся в точках не со степенью два (обрывы данных), затем замкнутые кольца
    for point in sorted(neighbours, key=lambda p: len(neighbours[p]) == 2):
        for other in neighbours[point]:
            if (min(point, other), max(point, other)) not in used:
                chains.append(walk(point, other))
    return chains


def _simplify(points, tolerance):
    """Дуглас-Пекер без рекурсии."""
    if len(points) < 3:
        return points
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = points[first], points[last]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        far, index = 0.0, None
        for i in range(first + 1, last):
            x, y = points[i]
            dist = math.hypot(x - x1, y - y1) if not norm else abs(dy * (x - x1) - dx * (y - y1)) / norm
            if dist > far:
                far, index = dist, i
        if index is not None and far > tolerance:
            keep.add(index)
            stack.extend([(first, index), (index, last)])
    return [points[i] for i in sorted(keep)]


def outer_boundary(rings_by_province):
    """{код: [кольца]} -> [[[lon, lat], ...], ...] внешние линии объединения."""
    counts = defaultdict(int)
    for rings in rings_by_province.values():
        for ring in rings:
            points = [(round(x * SCALE), round(y * SCALE)) for x, y in ring]
            for a, b in zip(points, points[1:]):
                if a != b:
                    counts[(a, b) if a < b else (b, a)] += 1

    lines = []
    for chain in _chains([edge for edge, n in counts.items() if n == 1]):
        points = [(x / SCALE, y / SCALE) for x, y in chain]
        points = _simplify(points, TOLERANCE)
        if len(points) >= 2:
            lines.append([[round(x, 4), round(y, 4)] for x, y in points])
    return lines


def outline_for(codes):
    """Линии внешней границы провинций с этими source_code (с кэшем: границы не меняются)."""
    from map.models import ProvinceShape

    codes = sorted(set(codes))
    if not codes:
        return []
    key = "map:outline:" + hashlib.md5(",".join(codes).encode()).hexdigest()
    lines = cache.get(key)
    if lines is None:
        ensure_shapes()
        shapes = dict(ProvinceShape.objects.filter(source_code__in=codes).values_list("source_code", "rings"))
        lines = outer_boundary(shapes)
        if lines:      # пустой ответ не запоминаем: контуры могут появиться после загрузки
            cache.set(key, lines, CACHE_SECONDS)
    return lines


def ensure_shapes():
    """Контуры провинций ещё не загружены: один раз читаем их из GeoJSON в репозитории (около 7 секунд).
    Тот же результат даёт команда import_province_shapes; здесь страховка на случай, если её не запускали."""
    from django.core.management import call_command

    from map.models import ProvinceShape

    if ProvinceShape.objects.exists() or not cache.add("map:shapes-importing", 1, 600):
        return
    try:
        call_command("import_province_shapes", verbosity=0)
    except OSError:
        pass
    finally:
        cache.delete("map:shapes-importing")
