"""Общий мир: триггеры, моменты и журнал. Метки и счётчики мира — теги и счётчики владельца «мир» (engine.values), логика в world/state.py.

В условиях доступа (secure.access) они пишутся строками: «world:core-online» (метка стоит), «world:fragments>=7» (счётчик)."""
from django.conf import settings
from django.db import models


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


class WorldMoment(models.Model):
    """Момент мира: событие в игровом времени (один раз или по расписанию). Пока идёт, стоит метка world:<имя>, по окончании снимается.
    Видимый момент игроки видят заранее: команда at, полоса на столе, {next_event}. Логика в world/moments.py."""

    name = models.SlugField("Имя (метка)", max_length=64, unique=True)
    label = models.CharField("Подпись для авторов", max_length=200, blank=True)
    title = models.CharField("Название для игроков", max_length=80, blank=True, help_text="Как его видят игроки: «BOREAS UPLINK».")
    schedule = models.TextField("Когда", help_text="Как у станций: «once 2031-03-01 21:00», «daily 21:00», «mon,fri 22:00».")
    time_zone = models.CharField("Часовой пояс", max_length=64, default="UTC")
    duration = models.PositiveIntegerField("Длится, минут", default=30)
    in_list = models.BooleanField("В at и {next_event}", default=False, help_text="Игроки видят его в списке at и в приветствии ОС.")
    ticker = models.BooleanField("Бегущая строка", default=False, help_text="Жёлтая строка у верхнего края стола: за «предупреждать за» до начала и пока идёт.")
    toast = models.BooleanField("Уведомление", default=False, help_text="Жёлтое уведомление на столе: за «предупреждать за» до начала и в момент начала.")
    warn = models.PositiveIntegerField("Предупреждать за, минут", default=15, help_text="Когда появляются строка и уведомление «скоро». 0: только в момент начала.")
    systems = models.JSONField("Только ОС", default=list, blank=True)
    machines = models.JSONField("Только машины", default=list, blank=True, help_text="Хосты.")
    groups = models.JSONField("Только группы", default=list, blank=True, help_text="Группы учётки, с которой игрок сидит на машине.")
    condition = models.JSONField("Кому виден", null=True, blank=True, help_text="Условие на ключи и мир. Пусто: всем, кто прошёл фильтры.")
    active = models.BooleanField("Включён", default=True)
    started_at = models.DateTimeField("Начался (игровое UTC)", null=True, blank=True)
    ends_at = models.DateTimeField("Кончится (игровое UTC)", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Момент мира"
        verbose_name_plural = "Моменты мира"

    def __str__(self):
        return self.name


class WorldLetter(models.Model):
    """Письмо всем игрокам по триггеру: в каждую учётку игрока на подходящей машине один раз, при следующем открытии её почты.
    Сюжетные учётки его не получают."""

    item = models.ForeignKey("filesystem.Item", on_delete=models.CASCADE, related_name="+")
    systems = models.JSONField(default=list, blank=True)
    machines = models.JSONField(default=list, blank=True)
    condition = models.JSONField(null=True, blank=True, help_text="Кому: условие по ключам и меткам мира. Пусто: всем.")
    source = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("pk",)


class WorldLetterDelivery(models.Model):
    letter = models.ForeignKey(WorldLetter, on_delete=models.CASCADE, related_name="deliveries")
    profile = models.ForeignKey("machines.MachineProfile", on_delete=models.CASCADE, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("letter", "profile"), name="unique_world_letter_profile")]
