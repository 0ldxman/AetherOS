import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from map.models import ProvinceShape

DEFAULT_PATH = Path(settings.BASE_DIR) / "map" / "static" / "data" / "aether_provinces.geojson"


def _rings(geometry):
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    return [[[round(x, 5), round(y, 5)] for x, y in ring] for polygon in polygons for ring in polygon]


class Command(BaseCommand):
    help = "Загрузить контуры провинций из GeoJSON в базу (для внешней границы выделений в сохранённых картах)"

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(DEFAULT_PATH), help="aether_provinces.geojson")

    def handle(self, *args, **options):
        with open(options["path"], encoding="utf-8") as f:
            data = json.load(f)

        shapes = {}
        for feature in data["features"]:
            code = (feature.get("properties") or {}).get("adm1_code")
            if code and feature.get("geometry"):
                shapes[code] = ProvinceShape(source_code=code, rings=_rings(feature["geometry"]))

        ProvinceShape.objects.all().delete()
        ProvinceShape.objects.bulk_create(shapes.values(), batch_size=200)
        self.stdout.write(self.style.SUCCESS(f"Контуров провинций: {len(shapes)}"))
