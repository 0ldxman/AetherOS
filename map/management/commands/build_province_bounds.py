import json
from pathlib import Path

from django.core.management.base import BaseCommand

from map.bounds import BOUNDS_FILE


def _ring_bbox(ring):
    lons = [point[0] for point in ring]
    lats = [point[1] for point in ring]
    return [min(lons), min(lats), max(lons), max(lats)]


def feature_bbox(geometry):
    """Рамка провинции [запад, юг, восток, север]. У мультиполигона берётся самый крупный
    кусок: острова и дальние эксклавы не растягивают рамку на полмира."""
    kind = geometry["type"]
    polygons = geometry["coordinates"] if kind == "MultiPolygon" else [geometry["coordinates"]]
    boxes = [_ring_bbox(polygon[0]) for polygon in polygons if polygon]
    return max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))


class Command(BaseCommand):
    help = "Собрать рамки провинций (adm1_code -> bbox) из GeoJSON для виджета ::map в вики"

    def add_arguments(self, parser):
        parser.add_argument("path", help="Путь к aether_provinces.geojson")

    def handle(self, *args, **options):
        with open(options["path"], encoding="utf-8") as f:
            data = json.load(f)

        bounds = {}
        for feature in data["features"]:
            code = (feature.get("properties") or {}).get("adm1_code")
            if code and feature.get("geometry"):
                bounds[code] = [round(v, 3) for v in feature_bbox(feature["geometry"])]

        Path(BOUNDS_FILE).write_text(json.dumps(bounds, separators=(",", ":")), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Рамок: {len(bounds)} -> {BOUNDS_FILE}"))
