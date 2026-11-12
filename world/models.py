"""Общий мир: метки и счётчики, одни на всех игроков, триггеры на них и журнал. Логика в world/state.py.

В условиях доступа (secure.access) они пишутся строками: «world:core-online» (метка стоит), «world:fragments>=7» (счётчик)."""
from django.conf import settings
from django.db import models


class WorldFlag(models.Model):
    name = models.SlugField("Имя", max_length=64, unique=True)
    label = models.CharField("Подпись для авторов", max_length=200, blank=True)
    on = models.BooleanField("Стоит", default=False)
    changed_at = models.DateTimeField("Изменена", null=True, blank=True)
    changed_by = models.CharField("Кем", max_length=200, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Мировая метка"
        verbose_name_plural = "Мировые метки"

    def __str__(self):
        return f"world:{self.name}"


class WorldCounter(models.Model):
    class Mode(models.TextChoices):
        SUM = "sum", "Сумма вкладов"
        PLAYERS = "players", "Каждый игрок один раз"

    name = models.SlugField("Имя", max_length=64, unique=True)
    label = models.CharField("Подпись для авторов", max_length=200, blank=True)
    mode = models.CharField("Как считать", max_length=16, choices=Mode.choices, default=Mode.SUM)
    value = models.IntegerField("Значение", default=0)
    changed_at = models.DateTimeField("Изменён", null=True, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Счётчик мира"
        verbose_name_plural = "Счётчики мира"

    def __str__(self):
        return f"world:{self.name}={self.value}"


class WorldContribution(models.Model):
    """Вклад в счётчик: кто, сколько, откуда."""

    counter = models.ForeignKey(WorldCounter, on_delete=models.CASCADE, related_name="contributions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    delta = models.IntegerField(default=1)
    source = models.CharField("Откуда", max_length=200, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-at", "-pk")
        indexes = [models.Index(fields=("counter", "user"), name="world_contrib_user_idx")]


class WorldTrigger(models.Model):
    """Когда условие на мир становится верным, выполняются действия. Повторный: срабатывает каждый раз, когда условие снова стало верным."""

    name = models.SlugField("Имя", max_length=64, unique=True)
    label = models.CharField("Подпись для авторов", max_length=200, blank=True)
    condition = models.JSONField("Условие", help_text="Строки world:метка и world:счётчик>=N, можно all / any / not.")
    actions = models.JSONField("Действия", default=list, blank=True)
    repeat = models.BooleanField("Повторный", default=False)
    active = models.BooleanField("Включён", default=True)
    was_true = models.BooleanField(default=False, help_text="Условие было верным при прошлой проверке: срабатывание только на переходе.")
    fired_at = models.DateTimeField("Сработал", null=True, blank=True)
    fired_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("name",)
        verbose_name = "Триггер мира"
        verbose_name_plural = "Триггеры мира"

    def __str__(self):
        return self.name


class WorldEvent(models.Model):
    """Журнал мира: что поменялось, кем и из-за чего."""

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(max_length=32)            # flag, counter, trigger, action
    subject = models.CharField(max_length=64, blank=True)
    text = models.CharField(max_length=400)
    source = models.CharField(max_length=200, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("-at", "-pk")
