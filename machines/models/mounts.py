from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class MachineMount(models.Model):
    """Монтирование: машина подключает том (или его папку) в точку своей файловой системы."""

    class Mode(models.TextChoices):
        LOCAL = "local", "Локально"
        REMOTE = "remote", "По сети"

    machine = models.ForeignKey("machines.Machine", on_delete=models.CASCADE, related_name="mounts")
    volume = models.ForeignKey(
        "filesystem.Volume", null=True, blank=True, on_delete=models.CASCADE, related_name="mounts",
        help_text="Только для локального монтирования.",
    )
    host = models.ForeignKey(
        "machines.Machine", null=True, blank=True, on_delete=models.CASCADE, related_name="remote_mounts", verbose_name="Хост",
        help_text="Только для монтирования по сети: машина, чей путь подключается.",
    )
    host_path = models.CharField(
        "Путь на хосте", max_length=2048, blank=True, help_text="Только по сети: что подключается. Хост должен отдавать этот путь (экспорт).",
    )
    account = models.ForeignKey(
        "machines.MachineProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="remote_mounts", verbose_name="Учётка",
        help_text="Только по сети: запись хоста, под которой идёт работа с диском. Пусто: запись guest, если она у хоста есть.",
    )
    volume_path = models.CharField(
        "Папка тома", max_length=2048, blank=True, help_text="Какая папка внутри тома монтируется. Пусто: весь том.",
    )
    mount_path = models.CharField(
        "Точка монтирования", max_length=2048, blank=True,
        help_text="Куда монтируется на машине: /mnt/harbor или диск C:. Пусто: в файловую систему том не попадает.",
    )
    mode = models.CharField("Режим", max_length=8, choices=Mode.choices, default=Mode.LOCAL)
    order = models.PositiveSmallIntegerField(
        "Порядок", default=0,
        help_text="Если на одну точку смонтировано несколько томов, они складываются стопкой: больший порядок лежит выше.",
    )

    class Meta:
        ordering = ("machine", "mount_path", "order", "id")
        verbose_name = "Монтирование"
        verbose_name_plural = "Монтирования"
        constraints = [
            models.UniqueConstraint(fields=("machine", "mount_path", "order"), condition=~Q(mount_path=""), name="unique_mount_layer"),
        ]

    def __str__(self):
        source = f"{self.host.label}:{self.host_path}" if self.mode == self.Mode.REMOTE and self.host_id else (self.volume.slug if self.volume_id else "?")
        return f"{self.machine.label}: {source} -> {self.mount_path or '(без точки)'}"

    def normalize(self):
        from filesystem.names import normalize_inner, normalize_mount

        self.volume_path = normalize_inner(self.volume_path)
        self.host_path = "/" + normalize_inner(self.host_path) if self.host_path.strip() else ""
        self.mount_path = normalize_mount(self.mount_path)

    def clean(self):
        super().clean()
        self.normalize()
        if self.mode == self.Mode.LOCAL and not self.volume_id:
            raise ValidationError({"volume": "Для локального монтирования нужен том."})
        if self.mode == self.Mode.REMOTE:
            if not self.host_id:
                raise ValidationError({"host": "Для монтирования по сети нужен хост."})
            if self.host_id == self.machine_id:
                raise ValidationError({"host": "Машина не подключает сама себя."})
            if not self.host_path:
                raise ValidationError({"host_path": "Укажите путь на хосте."})
            if self.account_id and self.account.machine_id != self.host_id:
                raise ValidationError({"account": "Учётка должна быть записью хоста."})

    def save(self, *args, **kwargs):
        self.normalize()
        super().save(*args, **kwargs)


class Export(models.Model):
    """Путь, который машина отдаёт по сети: подключиться можно к нему и к тому, что под ним (как /etc/exports)."""

    machine = models.ForeignKey("machines.Machine", on_delete=models.CASCADE, related_name="exports")
    path = models.CharField("Путь", max_length=2048, help_text="Путь в файловой системе машины: /srv/harbor. Корень отдаёт всё.")

    class Meta:
        ordering = ("machine", "path")
        verbose_name = "Экспорт"
        verbose_name_plural = "Экспорты"
        constraints = [models.UniqueConstraint(fields=("machine", "path"), name="unique_export")]

    def __str__(self):
        return f"{self.machine.label}: {self.path}"

    def save(self, *args, **kwargs):
        from filesystem.names import normalize_inner

        self.path = "/" + normalize_inner(self.path)
        super().save(*args, **kwargs)


class PlayerMount(models.Model):
    """Сетевой диск, который игрок подключил на машине сам (mnt): виден только ему, пока учётка хоста не сменила пароль."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="player_mounts")
    machine = models.ForeignKey("machines.Machine", on_delete=models.CASCADE, related_name="player_mounts")
    host = models.ForeignKey("machines.Machine", on_delete=models.CASCADE, related_name="+")
    host_path = models.CharField(max_length=2048)
    account = models.ForeignKey("machines.MachineProfile", on_delete=models.CASCADE, related_name="+")
    mount_path = models.CharField(max_length=2048)
    secret = models.CharField("Отпечаток пароля", max_length=128, blank=True, help_text="Хэш пароля учётки в момент подключения: сменился, диск пропал.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Диск игрока"
        verbose_name_plural = "Диски игроков"
        constraints = [models.UniqueConstraint(fields=("user", "machine", "mount_path"), name="unique_player_mount")]

    def __str__(self):
        return f"{self.user_id}@{self.machine_id}: {self.host_id}:{self.host_path} -> {self.mount_path}"

    def as_mount(self):
        """Монтирование для вида машины: несохранённая запись MachineMount с отрицательным id (уникальным среди обычных)."""
        return MachineMount(
            id=-self.pk, machine_id=self.machine_id, mode=MachineMount.Mode.REMOTE, host_id=self.host_id, host_path=self.host_path,
            account_id=self.account_id, mount_path=self.mount_path, order=1000,
        )
