import secrets

from django.core.exceptions import ValidationError
from django.db import models


def generate_hid():
    return ":".join(f"{secrets.randbelow(256):02x}" for _ in range(6))


class Machine(models.Model):
    class Status(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        OFFLINE = "OFFLINE", "Offline"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
    
    id = models.BigAutoField(primary_key=True)

    name = models.CharField(
        max_length=255,
    )

    system = models.CharField(
        max_length=32,
        default="AETHER",
        help_text="Код типа системы (SystemType.code): по нему выбираются сцены и команды.",
    )

    hostname = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    is_system = models.BooleanField(
        default=False,
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.OFFLINE,
    )

    hid = models.CharField(
        max_length=17,
        unique=True,
        blank=True,
    )

    callsign = models.CharField(
        "Позывной", max_length=32, blank=True, help_text="Как узел называет себя в эфире. Пусто: считается из hid.",
    )

    note = models.TextField(
        "Заметка", blank=True, help_text="Свободный текст о машине; ОС подставляет его в приветствие как {note}. Хорошее место для подсказки.",
    )

    booted_at = models.DateTimeField(
        "Включена", null=True, blank=True, help_text="С какого момента работает машина; от него считается {uptime}. Пусто: неизвестно.",
    )

    entry_policy = models.ForeignKey(
        "machines.EntryPolicy", null=True, blank=True, on_delete=models.SET_NULL, related_name="machines", verbose_name="Политика входа",
        help_text="Для записей машины, у которых своей политики нет. Пусто: политика типа системы.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    @property
    def system_type(self):
        """Запись типа системы этой машины или None, если такого кода в БД нет."""
        from machines import memo
        from machines.models.system import SystemType

        return memo.cached(("system-type", self.system), lambda: SystemType.objects.filter(code=self.system).first())

    @property
    def path_style(self):
        found = self.system_type
        return found.path_style if found else "unix"

    @property
    def label(self):
        """Короткое имя для строк: hostname, а если его нет, название."""
        return self.hostname or self.name

    def __str__(self):
        if self.hostname and self.hostname != self.name:
            return f"{self.name} ({self.hostname})"
        return self.name

    def save(self, *args, **kwargs):
        if not self.hid:
            self.hid = generate_hid()

        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        if self.is_system:
            raise ValidationError(
                f"Machine '{self.hostname}' is protected and cannot be deleted."
            )

        return super().delete(*args, **kwargs)
