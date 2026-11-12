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
    labels = models.JSONField("Подписи значений", default=dict, blank=True, help_text="{\"1\": \"Тишина\", \"2\": \"Архив\"}: для актов и уровней тревоги.")

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


class WorldMoment(models.Model):
    """Момент мира: событие в игровом времени (один раз или по расписанию). Пока идёт, стоит метка world:<имя>, по окончании снимается.
    Видимый момент игроки видят заранее: команда at, полоса на столе, {next_event}. Логика в world/moments.py."""

    name = models.SlugField("Имя (метка)", max_length=64, unique=True)
    label = models.CharField("Подпись для авторов", max_length=200, blank=True)
    title = models.CharField("Название для игроков", max_length=80, blank=True, help_text="Как его видят игроки: «BOREAS UPLINK».")
    schedule = models.TextField("Когда", help_text="Как у станций: «once 2031-03-01 21:00», «daily 21:00», «mon,fri 22:00».")
    time_zone = models.CharField("Часовой пояс", max_length=64, default="UTC")
    duration = models.PositiveIntegerField("Длится, минут", default=30)
    public = models.BooleanField("Виден игрокам", default=False)
    warn = models.PositiveIntegerField("Предупреждать за, минут", default=0, help_text="Полоса на столе за столько минут до начала. 0: без полосы.")
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
    """Письмо всем по триггеру: приходит каждому игроку один раз, при следующем открытии почты на подходящей машине."""

    item = models.ForeignKey("filesystem.Item", on_delete=models.CASCADE, related_name="+")
    systems = models.JSONField(default=list, blank=True)
    machines = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("pk",)


class WorldLetterDelivery(models.Model):
    letter = models.ForeignKey(WorldLetter, on_delete=models.CASCADE, related_name="deliveries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("letter", "user"), name="unique_world_letter_user")]
