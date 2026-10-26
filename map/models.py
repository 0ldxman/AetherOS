from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q

class Country(models.Model):
    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=128)
    color = models.CharField(
        max_length=7,
        default="#cccccc",
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Формат цвета: #RRGGBB")],
    )
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    predecessor = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="successors",
    )

    wiki_url = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="country_valid_to_gte_valid_from",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Province(models.Model):
    code = models.CharField(max_length=32, unique=True)
    source_code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)

    wiki_url = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Ownership(models.Model):
    province = models.ForeignKey(
        Province,
        on_delete=models.CASCADE,
        related_name="ownerships",
    )

    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="owned_provinces",
    )

    date_from = models.DateField()

    de_jure = models.BooleanField(default=False)
    de_facto = models.BooleanField(default=False)

    class Meta:
        ordering = ["province", "date_from"]
        indexes = [
            models.Index(fields=["date_from"], name="ownership_date_from_idx"),   # выбор на дату и засечки таймлайна
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["province", "country", "date_from"],
                name="unique_ownership_start",
            ),
            models.CheckConstraint(
                condition=Q(de_jure=True) | Q(de_facto=True),
                name="ownership_has_jure_or_facto",
            ),
        ]

    def __str__(self):
        return f"{self.province} → {self.country} с {self.date_from}"


class CountryLabel(models.Model):
    """Подпись страны на карте. У одной страны может быть несколько подписей
    (основная территория, острова, заморские владения)."""

    # Ранги совпадают с ключами LABEL_RANKS в map.js (размер и зум показа)
    class Rank(models.IntegerChoices):
        MAJOR = 1, "Крупная"
        MEDIUM = 2, "Средняя"
        SMALL = 3, "Малая"
        TINY = 4, "Мелкая"

    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name="labels",
    )
    text = models.CharField(
        "Текст",
        max_length=128,
        blank=True,
        help_text="Пусто - берётся название страны",
    )
    lng = models.FloatField(
        "Долгота",
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    lat = models.FloatField(
        "Широта",
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    rank = models.PositiveSmallIntegerField(
        "Ранг",
        choices=Rank.choices,
        default=Rank.MEDIUM,
    )

    class Meta:
        ordering = ["country", "rank", "id"]

    @property
    def display_text(self):
        return self.text or self.country.name

    def __str__(self):
        return f"{self.display_text} ({self.lng}, {self.lat})"

class MapScene(models.Model):
    """Сохранённая карта: дата мира, камера и слой пометок (маркеры, линии, стрелки, фигуры, подписи)."""

    class Mode(models.TextChoices):
        POLITICAL = "political", "Политическая"
        PHYSICAL = "physical", "Физическая"

    slug = models.SlugField("Слаг", unique=True, max_length=64)
    title = models.CharField("Название", max_length=128)

    base_date = models.DateField(
        "Дата мира", null=True, blank=True,
        help_text="Владения провинций на эту дату. Пусто: самые свежие.",
    )
    mode = models.CharField("Режим", max_length=16, choices=Mode.choices, default=Mode.POLITICAL)

    lat = models.FloatField("Широта центра", default=20, validators=[MinValueValidator(-85), MaxValueValidator(85)])
    lon = models.FloatField("Долгота центра", default=10, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    zoom = models.FloatField("Зум", default=3, validators=[MinValueValidator(0), MaxValueValidator(18)])

    bounds = models.JSONField(
        "Границы камеры", null=True, blank=True,
        help_text="[запад, юг, восток, север]: за эту область камера не уходит.",
    )
    min_zoom = models.FloatField("Минимальный зум", null=True, blank=True)
    max_zoom = models.FloatField("Максимальный зум", null=True, blank=True)
    flat = models.BooleanField("Плоская карта", default=False, help_text="2D вместо глобуса.")

    features = models.JSONField("Пометки", default=list, blank=True)
    thumbnail = models.TextField(
        "Миниатюра", blank=True,
        help_text="Картинка-превью для списка (data:image/jpeg), снимается редактором при сохранении.",
    )
    key_condition = models.JSONField("Условие по ключам", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "сохранённая карта"
        verbose_name_plural = "сохранённые карты"

    def __str__(self):
        return f"{self.title} ({self.slug})"

    def clean(self):
        from django.core.exceptions import ValidationError

        from secure.access import validate_requirements

        from .scenes import clean_features

        self.features = clean_features(self.features)
        if self.thumbnail and not (
            self.thumbnail.startswith("data:image/jpeg;base64,") and len(self.thumbnail) <= 120_000
        ):
            raise ValidationError({"thumbnail": "Миниатюра это data:image/jpeg;base64 не больше 120 КБ."})
        validate_requirements(self.key_condition)
        if self.bounds is not None:
            ok = (
                isinstance(self.bounds, list) and len(self.bounds) == 4
                and all(isinstance(v, (int, float)) for v in self.bounds)
                and self.bounds[0] < self.bounds[2] and self.bounds[1] < self.bounds[3]
            )
            if not ok:
                raise ValidationError({"bounds": "Нужно [запад, юг, восток, север], запад меньше востока, юг меньше севера."})
        if self.min_zoom is not None and self.max_zoom is not None and self.min_zoom > self.max_zoom:
            raise ValidationError({"max_zoom": "Максимальный зум меньше минимального."})


class MapSceneRevision(models.Model):
    """Снимок сохранённой карты после очередного сохранения (для отката)."""

    scene = models.ForeignKey(MapScene, on_delete=models.CASCADE, related_name="revisions")
    saved_at = models.DateTimeField(auto_now_add=True)
    saved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    data = models.JSONField()

    class Meta:
        ordering = ["-saved_at", "-id"]


class ProvinceShape(models.Model):
    """Контуры провинции из aether_provinces.geojson: нужны, чтобы склеить внешнюю границу страны (границы между
    выбранными провинциями сокращаются, остаётся граница их объединения). Заполняется командой import_province_shapes."""

    source_code = models.CharField(max_length=64, unique=True)
    rings = models.JSONField("Кольца", help_text="[[[lon, lat], ...], ...]: все кольца провинции, окружности и дыры.")

    def __str__(self):
        return self.source_code
