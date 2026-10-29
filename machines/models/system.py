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

    class Meta:
        ordering = ("code",)
        verbose_name = "Тип системы"
        verbose_name_plural = "Типы систем"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Place(models.Model):
    """Системный путь: именованное место, имя и шаблон пути (secrets, desktop, trash, config, logs, temp...).

    Значения типа системы задают умолчание, машина может переопределить. Какие имена знает движок и что в них по умолчанию,
    см. machines/places.py. В шаблоне: {login} (логин записи) и {home} (место home)."""

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
        from machines.dialect import to_canonical

        if (self.system_type_id is None) == (self.machine_id is None):
            raise ValidationError("Место задаётся либо для типа системы, либо для машины.")
        self.path = to_canonical(self.path)
        if not self.path:
            raise ValidationError({"path": "Укажите путь."})

    def save(self, *args, **kwargs):
        from machines.dialect import to_canonical

        self.path = to_canonical(self.path)
        super().save(*args, **kwargs)
