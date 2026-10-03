from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models import Q

from secure.models import Key


class DesktopApp(models.Model):
    """Приложение, которое может стоять на машине (иконка на рабочем столе)."""

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=60)
    icon = models.CharField(max_length=200, blank=True)  # символ или путь к картинке
    url = models.CharField(max_length=200)  # что открывать в окне

    def __str__(self):
        return self.title


class Machine(models.Model):
    name = models.CharField(max_length=100)
    ip = models.CharField(max_length=64, unique=True)  # вымышленный адрес
    login = models.CharField(max_length=50)
    password = models.CharField(max_length=128)  # только хеш, см. set_password()
    style = models.SlugField(default="default")  # имя темы оформления рабочего стола
    # ключи, которые "лежат" на машине: действуют только в сессии на ней
    keys = models.ManyToManyField(Key, blank=True, related_name="machines")
    # ключи, которыми можно войти на машину вместо пароля (ssh <ip> --k <ключ>)
    authorized_keys = models.ManyToManyField(
        Key, blank=True, related_name="opens_machines"
    )
    apps = models.ManyToManyField(
        DesktopApp, through="MachineApp", blank=True, related_name="machines"
    )

    def __str__(self):
        return f"{self.name} ({self.ip})"

    def set_password(self, raw):
        self.password = make_password(raw)

    def check_password(self, raw):
        return check_password(raw, self.password)


class MachineApp(models.Model):
    """Приложение на конкретной машине."""

    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="machine_apps"
    )
    app = models.ForeignKey(DesktopApp, on_delete=models.CASCADE)
    requirements = models.JSONField(default=dict, blank=True)  # условие показа иконки
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["machine", "app"], name="unique_machine_app"
            ),
        ]

    def __str__(self):
        return f"{self.machine.name}: {self.app.title}"


class MachineSession(models.Model):
    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="sessions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="machine_sessions",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)  # NULL = сессия активна

    class Meta:
        constraints = [
            # у игрока может быть только одна активная сессия
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(ended_at__isnull=True),
                name="one_active_session_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.machine.name}"