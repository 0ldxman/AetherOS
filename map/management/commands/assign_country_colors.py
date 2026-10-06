import colorsys
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from ...models import Country

DEFAULT_COLOR = "#cccccc"
GOLDEN_RATIO = 0.618033988749895


def random_colors(count):
    """Случайные, но заметно различающиеся цвета: оттенки идут шагом золотого сечения."""
    hue = random.random()
    for _ in range(count):
        hue = (hue + GOLDEN_RATIO) % 1
        saturation = random.uniform(0.5, 0.8)
        value = random.uniform(0.7, 0.95)
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
        yield f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


class Command(BaseCommand):
    help = "Раздаёт странам случайные цвета"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Перекрасить все страны, а не только с цветом по умолчанию",
        )

    def handle(self, *args, **options):
        countries = Country.objects.all()
        if not options["force"]:
            countries = countries.filter(color=DEFAULT_COLOR)

        countries = list(countries)
        for country, color in zip(countries, random_colors(len(countries))):
            country.color = color

        with transaction.atomic():
            Country.objects.bulk_update(countries, ["color"])

        self.stdout.write(self.style.SUCCESS(f"Покрашено стран: {len(countries)}"))