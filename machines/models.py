from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models import Q

from secure.models import Key
import secrets

from django.core.exceptions import ValidationError

from .paths import validate_internal_path


def generate_hid():
    return ":".join(f"{secrets.randbelow(256):02x}" for _ in range(6))


class Machine(models.Model):
    class Status(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        OFFLINE = "OFFLINE", "Offline"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
    
    class MachineSystem(models.TextChoices):
        AETHER = "AETHER", "Aether"

    id = models.BigAutoField(primary_key=True)

    name = models.CharField(
        max_length=255,
    )

    system = models.CharField(
        max_length=32,
        choices=MachineSystem.choices,
        default=MachineSystem.AETHER,
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

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

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


class MachineProfile(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )

    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.CASCADE,
        related_name="profiles",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="machine_profiles",
    )

    name = models.CharField(
        max_length=255,
    )

    freq = models.DecimalField(
        max_digits=6,
        decimal_places=3,
    )

    login = models.CharField(
        max_length=128,
    )

    password_hash = models.CharField(
        max_length=128,
        blank=True,
    )

    key_condition = models.JSONField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("machine", "login", "freq")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "machine",
                    "login",
                    "freq",
                ),
                name="unique_machine_profile_endpoint",
            ),
        ]

    def __str__(self):
        return f"{self.login}@{self.machine.label}:{self.freq:.3f}"


class MachineProfileToken(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )

    profile = models.ForeignKey(
        MachineProfile,
        on_delete=models.CASCADE,
        related_name="tokens",
    )

    token = models.CharField(
        max_length=255,
        unique=True,
    )

    max_usage = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    usage = models.PositiveIntegerField(
        default=0,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.profile.login} / {self.token}"


class MachineProfileHID(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )

    profile = models.ForeignKey(
        MachineProfile,
        on_delete=models.CASCADE,
        related_name="allowed_hids",
    )

    hid = models.CharField(
        max_length=17,
    )

    class Meta:
        ordering = ("profile", "hid")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "profile",
                    "hid",
                ),
                name="unique_profile_hid",
            ),
        ]

    def __str__(self):
        return self.hid


class Session(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sessions",
    )

    profile = models.ForeignKey(
        "machines.MachineProfile",
        on_delete=models.CASCADE,
        related_name="sessions",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return f"{self.user} @ {self.profile}"


class MachineApp(models.Model):
    id = models.BigAutoField(primary_key=True)

    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.CASCADE,
        related_name="machine_apps",
    )

    label = models.CharField(max_length=64)
    glyph = models.CharField(max_length=8)
    suffix = models.CharField(max_length=16, blank=True)

    path = models.CharField(max_length=512)

    order = models.PositiveSmallIntegerField(default=0)

    key_condition = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ("machine", "order", "id")

    def __str__(self):
        return f"{self.machine.label}: {self.label}"

    def clean(self):
        validate_internal_path(self.path)
