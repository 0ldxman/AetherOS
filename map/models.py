from django.core.validators import RegexValidator
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