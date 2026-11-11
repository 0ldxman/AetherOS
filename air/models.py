"""Эфир: открытый радиоэфир сети узлов. Игроки слушают и передают почти на любой частоте; приватность в том, чтобы найти
свободную. Слушатель видит только то, что пришло после его выхода на частоту. Система хранит передачи 24 часа (модерация и скан).
Логика в air/radio.py."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Callsign(models.Model):
    """Позывной игрока в эфире. Настоящее имя (Discord) видят только авторы."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="callsign")
    name = models.CharField("Позывной", max_length=16, unique=True)
    changed_at = models.DateTimeField("Сменён игроком", null=True, blank=True)
    muted_until = models.DateTimeField("Заглушён до", null=True, blank=True)
    rx_only = models.BooleanField("Только приём", default=False, help_text="Передатчик отобран: игрок слушает, но не передаёт.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Позывной"
        verbose_name_plural = "Позывные"

    def __str__(self):
        return self.name


class CallsignChange(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="callsign_changes")
    old = models.CharField(max_length=16)
    new = models.CharField(max_length=16)
    at = models.DateTimeField(auto_now_add=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                           help_text="Автор, если сменил он; пусто: сам игрок.")

    class Meta:
        ordering = ("-at", "-pk")


class Station(models.Model):
    """Станция или персонаж: от их имени передают авторы. Имя зарезервировано, игрок его не займёт."""

    class Kind(models.TextChoices):
        STATION = "station", "Станция"
        CHARACTER = "character", "Персонаж"

    name = models.CharField("Позывной", max_length=16, unique=True)
    label = models.CharField("Подпись для авторов", max_length=120, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.STATION)

    class Meta:
        ordering = ("name",)
        verbose_name = "Станция"
        verbose_name_plural = "Станции и персонажи"

    def __str__(self):
        return self.name


class Band(models.Model):
    """Полоса частот с особым правилом: зарезервирована (игроки не передают) или слышна только по условию на ключи."""

    class Kind(models.TextChoices):
        RESERVED = "reserved", "Зарезервирована"
        CONDITIONAL = "conditional", "Слышна по условию"

    low = models.DecimalField("С частоты", max_digits=6, decimal_places=3)
    high = models.DecimalField("По частоту", max_digits=6, decimal_places=3)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.RESERVED)
    condition = models.JSONField("Условие слушать", null=True, blank=True, help_text="Условие на ключи (secure.access). Пусто: слышат все.")
    label = models.CharField("Подпись", max_length=120, blank=True)

    class Meta:
        ordering = ("low",)
        verbose_name = "Полоса"
        verbose_name_plural = "Полосы"

    def __str__(self):
        return f"{self.low}–{self.high} {self.label}"


class Transmission(models.Model):
    freq = models.DecimalField("Частота", max_digits=6, decimal_places=3, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="transmissions")
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.CASCADE, related_name="transmissions")
    callsign = models.CharField("Позывной в момент передачи", max_length=16)
    machine = models.ForeignKey("machines.Machine", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    text = models.CharField(max_length=400)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    hidden_reason = models.CharField(max_length=200, blank=True)
    sandbox = models.BooleanField(default=False, help_text="Передал песочный игрок автора: слышит только его песочница.")

    class Meta:
        ordering = ("created_at", "pk")
        indexes = [models.Index(fields=("freq", "created_at"), name="air_freq_time_idx")]

    def __str__(self):
        return f"{self.freq} {self.callsign}: {self.text[:40]}"


class Report(models.Model):
    transmission = models.ForeignKey(Transmission, on_delete=models.CASCADE, related_name="reports")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="air_reports")
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("transmission", "user"), name="unique_air_report")]
