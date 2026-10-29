from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class SystemType(models.Model):
    """Тип системы: что общего у машин одной ОС. Код (AETHER) выбирает сцены и команды в Python, остальное задаётся здесь."""

    class PathStyle(models.TextChoices):
        UNIX = "unix", "Unix (/home/ivan)"
        WINDOWS = "windows", "Windows (C:\\Users\\ivan)"

    code = models.CharField("Код", max_length=32, unique=True, help_text="Большими буквами: AETHER. По нему выбираются сцены и команды.")
    name = models.CharField("Название", max_length=128)
    path_style = models.CharField(
        "Диалект путей", max_length=8, choices=PathStyle.choices, default=PathStyle.UNIX,
        help_text="Как машины этой системы показывают и принимают пути в терминале. Хранение от него не зависит.",
    )
    entry_policy = models.ForeignKey(
        "machines.EntryPolicy", null=True, blank=True, on_delete=models.SET_NULL, related_name="system_types", verbose_name="Политика входа",
        help_text="Для машин этого типа, у которых своей политики нет. Пусто: без ограничений.",
    )

    style = models.CharField(
        "Стиль", max_length=32, default="aether",
        help_text="Готовый стиль рабочего стола и окон: раскладка и вид элементов. Список в machines/world/styles.py.",
    )
    style_tokens = models.JSONField(
        "Токены стиля", default=dict, blank=True, help_text="Переопределения токенов (цвета, шрифты, форма) поверх стиля: {\"--accent\": \"#ff8800\"}.",
    )
    greeting = models.TextField(
        "Приветствие", blank=True,
        help_text="Что видит игрок, когда открывается оболочка. Цвета: <dim>, <success>, <warning>, <error>; подстановки: {host}, {login}... "
                  "Пусто: общее приветствие.",
    )

    class Meta:
        ordering = ("code",)
        verbose_name = "Тип системы"
        verbose_name_plural = "Типы систем"

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        super().clean()
        from scenes import markup
        from terminal.scenes.shell import GREETING_PARAMS

        from machines.world import styles

        looks = styles.problems(self.style, self.style_tokens)
        if looks:
            raise ValidationError({"style": looks})
        found = markup.check(self.greeting, GREETING_PARAMS)
        if found:
            raise ValidationError({"greeting": [f"Строка {number}: {text}" for number, text in found]})


class Place(models.Model):
    """Системный путь: именованное место, имя и шаблон пути (secrets, desktop, trash, config, logs, temp...).

    Значения типа системы задают умолчание, машина может переопределить. Какие имена знает движок и что в них по умолчанию,
    см. machines/world/places.py. В шаблоне: {login} (логин записи) и {home} (место home)."""

    system_type = models.ForeignKey("machines.SystemType", null=True, blank=True, on_delete=models.CASCADE, related_name="places")
    machine = models.ForeignKey("machines.Machine", null=True, blank=True, on_delete=models.CASCADE, related_name="places")
    name = models.SlugField("Имя", max_length=32, help_text="home, secrets, desktop, trash, config, logs, temp или своё.")
    path = models.CharField("Путь", max_length=512, help_text="Шаблон пути: {home}/.secrets или C:\\Users\\{login}.")

    class Meta:
        ordering = ("name",)
        verbose_name = "Системный путь"
        verbose_name_plural = "Системные пути"
        constraints = [
            models.CheckConstraint(
                condition=(Q(system_type__isnull=False, machine__isnull=True) | Q(system_type__isnull=True, machine__isnull=False)),
                name="place_system_xor_machine",
            ),
            models.UniqueConstraint(fields=("system_type", "name"), condition=Q(system_type__isnull=False), name="unique_system_place"),
            models.UniqueConstraint(fields=("machine", "name"), condition=Q(machine__isnull=False), name="unique_machine_place"),
        ]

    def __str__(self):
        return f"{self.system_type or self.machine}: {self.name} = {self.path}"

    def clean(self):
        super().clean()
        from machines.world.dialect import to_canonical

        if (self.system_type_id is None) == (self.machine_id is None):
            raise ValidationError("Место задаётся либо для типа системы, либо для машины.")
        self.path = to_canonical(self.path)
        if not self.path:
            raise ValidationError({"path": "Укажите путь."})

    def save(self, *args, **kwargs):
        from machines.world.dialect import to_canonical

        self.path = to_canonical(self.path)
        super().save(*args, **kwargs)


class SystemVolume(models.Model):
    """Образ системного диска: том, который получают все машины ОС, как будто они сами его смонтировали.

    Лежит под монтированиями самой машины: на одну точку они складываются стопкой, файлы машины перекрывают файлы образа."""

    system_type = models.ForeignKey("machines.SystemType", on_delete=models.CASCADE, related_name="volumes")
    volume = models.ForeignKey("filesystem.Volume", on_delete=models.CASCADE, related_name="system_volumes")
    volume_path = models.CharField("Папка тома", max_length=2048, blank=True, help_text="Какая папка внутри тома монтируется. Пусто: весь том.")
    mount_path = models.CharField("Точка монтирования", max_length=2048, help_text="Куда монтируется на машине: / или диск C:.")
    order = models.PositiveSmallIntegerField("Порядок", default=0, help_text="Если на одну точку несколько томов, больший порядок лежит выше.")

    class Meta:
        ordering = ("system_type", "mount_path", "order", "id")
        verbose_name = "Образ системного диска"
        verbose_name_plural = "Образы системных дисков"
        constraints = [models.UniqueConstraint(fields=("system_type", "mount_path", "order"), name="unique_system_volume_layer")]

    def __str__(self):
        return f"{self.system_type.code}: {self.volume.slug} -> {self.mount_path}"

    def normalize(self):
        from filesystem.names import normalize_inner, normalize_mount

        self.volume_path = normalize_inner(self.volume_path)
        self.mount_path = normalize_mount(self.mount_path)

    def clean(self):
        super().clean()
        self.normalize()
        if not self.mount_path:
            raise ValidationError({"mount_path": "Укажите точку монтирования."})

    def save(self, *args, **kwargs):
        self.normalize()
        super().save(*args, **kwargs)

    def as_mount(self, machine_id):
        """Монтирование для вида машины: несохранённая запись MachineMount с отрицательным id (вне диапазона дисков игрока).
        Порядок сдвинут вниз, чтобы свои монтирования машины всегда лежали выше образа."""
        from machines.models.mounts import MachineMount

        return MachineMount(
            id=-(10**9 + self.pk), machine_id=machine_id, volume_id=self.volume_id, volume_path=self.volume_path,
            mount_path=self.mount_path, mode=MachineMount.Mode.LOCAL, order=self.order - 100000,
        )


class SystemBlackout(models.Model):
    """Чёрный экран рабочего стола при подключении, закрытии подключения и обрыве по сроку: свои тексты и оформление ОС.

    Пустое поле значит «как у движка» (machines/world/blackout.py), своей записи нет: всё по умолчанию."""

    class Event(models.TextChoices):
        ARRIVE = "arrive", "Подключение"
        LEAVE = "leave", "Закрытие подключения"
        KICK = "kick", "Обрыв по сроку"

    class Tone(models.TextChoices):
        SUCCESS = "success", "Зелёный"
        WARNING = "warning", "Жёлтый"
        ERROR = "error", "Красный"
        DIM = "dim", "Серый"

    system_type = models.ForeignKey("machines.SystemType", on_delete=models.CASCADE, related_name="blackouts")
    event = models.CharField("Событие", max_length=8, choices=Event.choices)
    title = models.CharField("Заголовок окна", max_length=128, blank=True, help_text="Подстановки: {label}, {host}, {login}, {os}, {os_name}.")
    text = models.TextField("Текст", blank=True, help_text="Те же подстановки. У записи может быть свой текст обрыва: он важнее.")
    tone = models.CharField("Цвет", max_length=8, choices=Tone.choices, blank=True)
    delay_ms = models.PositiveIntegerField("Пауза до окна, мс", null=True, blank=True)
    speed_ms = models.PositiveIntegerField("Печать, мс на букву", null=True, blank=True)
    hold_ms = models.PositiveIntegerField("Пауза после текста, мс", null=True, blank=True)

    class Meta:
        ordering = ("system_type", "event")
        verbose_name = "Чёрный экран ОС"
        verbose_name_plural = "Чёрные экраны ОС"
        constraints = [models.UniqueConstraint(fields=("system_type", "event"), name="unique_system_blackout")]

    def __str__(self):
        return f"{self.system_type.code}: {self.event}"

    def clean(self):
        super().clean()
        from machines.world import blackout

        problems = blackout.check(self.title, self.text)
        if problems:
            raise ValidationError({"text": problems})
