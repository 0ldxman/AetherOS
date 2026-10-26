from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models import Q

from secure.models import Key
import secrets

from django.core.exceptions import ValidationError

from mail.addresses import validate_address

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
        "Частота / порт",
        max_digits=8,
        decimal_places=3,
        help_text="Где слушает эта запись: у систем Aether частота в МГц (14.230), у остальных порт (22).",
    )

    login = models.CharField(
        max_length=128,
    )

    mail = models.CharField(
        "Почта",
        max_length=255,
        validators=[validate_address],
        help_text="Адрес этого профиля, например will_smith@apollo.mail. Игрок под профилем читает и пишет от его лица.",
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

    def save(self, *args, **kwargs):
        if not self.mail:
            self.mail = f"{self.login}@{self.machine.label}"

        super().save(*args, **kwargs)


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


def normalize_suffix(value):
    """Расширение приложения всегда с точкой: «db» и «.db» это одно и то же «.db», пустое остаётся пустым."""
    value = (value or "").strip().lstrip(".")
    return f".{value}" if value else ""


class MachineApp(models.Model):
    id = models.BigAutoField(primary_key=True)

    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.CASCADE,
        related_name="machine_apps",
    )

    label = models.CharField(max_length=64)
    glyph = models.CharField(max_length=8)
    suffix = models.CharField(
        max_length=16,
        blank=True,
        help_text="Расширение после названия: db или .db (точка добавится сама). Можно не указывать.",
    )

    path = models.CharField(max_length=512)

    order = models.PositiveSmallIntegerField(default=0)

    key_condition = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ("machine", "order", "id")

    def __str__(self):
        return f"{self.machine.label}: {self.label}"

    def clean(self):
        self.suffix = normalize_suffix(self.suffix)
        validate_internal_path(self.path)

    def save(self, *args, **kwargs):
        self.suffix = normalize_suffix(self.suffix)
        super().save(*args, **kwargs)



class VolumeMount(models.Model):
    """Том вики (корневой неймспейс), смонтированный на машине.

    Машина видит в вики только свои тома; что из них открыто игроку, решают ключи, как раньше.
    Нет монтирований, значит и тома в вики ни одного: пустая вики.
    """

    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.CASCADE,
        related_name="volume_mounts",
    )

    namespace = models.ForeignKey(
        "wiki.Namespace",
        on_delete=models.CASCADE,
        related_name="mounts",
        limit_choices_to={"parent__isnull": True},
        verbose_name="Том",
        help_text="Корневой неймспейс.",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Порядок в дереве и на стартовой странице: меньше выше.",
    )

    class Meta:
        ordering = ("machine", "order", "id")
        constraints = [
            models.UniqueConstraint(fields=("machine", "namespace"), name="unique_volume_mount"),
        ]

    def __str__(self):
        return f"{self.machine_id}: {self.namespace_id}"

    def clean(self):
        if self.namespace_id and self.namespace.parent_id is not None:
            from django.core.exceptions import ValidationError

            raise ValidationError({"namespace": "Монтируется только корневой неймспейс (том)."})


class NetResource(models.Model):
    """Сетевой ресурс: то, к чему обращаются командами nreq и nget (внутриигровой «сервер»).

    Адрес это частота у Aether или имя у остальных систем, как его пишет игрок. Ресурс отвечает на nreq текстом автора
    и отдаёт на nget свои файлы: файл появляется в сессии игрока на той машине, где он набрал команду.
    Реальной сети нет, всё описывается здесь.
    """

    address = models.CharField(
        max_length=255,
        unique=True,
        help_text="Что вводит игрок: частота (14.230) или имя (archive.eclipse). Регистр не важен.",
    )
    title = models.CharField(max_length=128, blank=True, help_text="Название для админки; игрок его не видит.")
    response = models.TextField(
        blank=True,
        help_text="Ответ на nreq. Что угодно: приветствие сервера, баннер, текст ошибки.",
    )
    listing = models.BooleanField(
        default=True,
        help_text="Добавлять к ответу nreq список файлов, которые можно скачать. Выключите, если имена файлов нужно узнать иначе.",
    )
    key_condition = models.JSONField(
        null=True,
        blank=True,
        help_text="Без выполненного условия по ключам ресурс не находится: игроку он отвечает как несуществующий.",
    )
    token = models.CharField(
        max_length=255,
        blank=True,
        help_text="Если задан, ресурс отвечает только тому, кто назвал его в --token. Без него: 401.",
    )

    class Meta:
        ordering = ("address",)
        verbose_name = "Сетевой ресурс"
        verbose_name_plural = "Сетевые ресурсы"

    def __str__(self):
        return f"{self.address}" + (f" ({self.title})" if self.title else "")

    def save(self, *args, **kwargs):
        self.address = self.address.strip().lower()
        super().save(*args, **kwargs)


class NetResourceFile(models.Model):
    """Файл, который ресурс отдаёт по nget: файл машины-сервера под своим именем."""

    resource = models.ForeignKey(NetResource, on_delete=models.CASCADE, related_name="files")
    file = models.ForeignKey(
        "filesystem.MachineFile",
        on_delete=models.CASCADE,
        related_name="net_files",
        help_text="Обычно файл машины-сервера. Игрок получит его копию со всеми слоями в исходном состоянии.",
    )
    name = models.CharField(max_length=255, help_text="Под каким именем игрок его запрашивает и сохраняет.")

    class Meta:
        ordering = ("resource", "name")
        constraints = [models.UniqueConstraint(fields=("resource", "name"), name="unique_net_file_name")]

    def __str__(self):
        return f"{self.resource.address}/{self.name}"

