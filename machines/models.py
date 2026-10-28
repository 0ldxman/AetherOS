import re
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

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    @property
    def system_type(self):
        """Запись типа системы этой машины или None, если такого кода в БД нет."""
        return SystemType.objects.filter(code=self.system).first()

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

    ttl = models.PositiveIntegerField(
        "Срок подключения, с",
        null=True,
        blank=True,
        help_text="Сколько секунд держится подключение игрока на эту запись (с момента входа). Пусто: без ограничения.",
    )

    cooldown = models.PositiveIntegerField(
        "Блокировка после обрыва, с",
        null=True,
        blank=True,
        help_text="Сколько секунд после обрыва по сроку запись не принимает этого игрока (для него это блокировка аккаунта).",
    )

    kick_message = models.TextField(
        "Сообщение при обрыве",
        blank=True,
        help_text="Текст в окне на чёрном экране, когда игрока выбросило с рабочего стола этой записи. Пусто: стандартный для системы.",
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

    blocked_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Запись не принимает игрока до этого момента (после обрыва по сроку).",
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


LISTING_TAG = "{listing}"


SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*)://", re.I)


def normalize_address(text):
    """Адрес сервера как его хранят и ищут: схема (если есть) и имя строчными, без пути, запроса и конечных слэшей.
    https://Apollo.com/info/ -> https://apollo.com; apollo.com остаётся apollo.com (сервер для любой схемы)."""
    scheme, host, _ = split_url(text)
    return f"{scheme}://{host}" if scheme and host else host


def split_url(text):
    """(схема, адрес, путь) из того, что набрал игрок: https://apollo.com/info/ -> ("https", "apollo.com", "info").
    Схемы может не быть: тогда это пустая строка."""
    text = (text or "").strip()
    found = SCHEME.match(text)
    scheme = found.group(1).lower() if found else ""
    text = SCHEME.sub("", text, count=1)
    text = re.split(r"[?#]", text, maxsplit=1)[0]
    host, _, path = text.partition("/")
    return scheme, host.strip().lower(), "/".join(part for part in path.split("/") if part)


class NetResource(models.Model):
    """Сетевой ресурс: «сервер», к которому обращаются командами nreq и nget (внутриигровой, реальной сети нет).

    Адрес это частота у Aether или имя сервера (apollo.com) у остальных систем. Что на сервере лежит, описывают его
    узлы (NetNode): страницы с текстом и файлы по путям, как на сайте.
    """

    address = models.CharField(
        max_length=255,
        unique=True,
        help_text=(
            "Что вводит игрок: частота (14.230) или имя сервера (apollo.com). Регистр не важен. "
            "Со схемой (ftp://apollo.com) игрок должен набрать её; без схемы сервер отвечает на любую."
        ),
    )
    title = models.CharField(max_length=128, blank=True, help_text="Название для админки; игрок его не видит.")
    key_condition = models.JSONField(
        null=True,
        blank=True,
        help_text="Без выполненного условия по ключам сервер не находится: игроку он отвечает как несуществующий.",
    )
    token = models.CharField(
        max_length=255,
        blank=True,
        help_text="Если задан, сервер отвечает только тому, кто назвал его в --token. Без него: 401.",
    )

    class Meta:
        ordering = ("address",)
        verbose_name = "Сетевой ресурс"
        verbose_name_plural = "Сетевые ресурсы"

    def __str__(self):
        return f"{self.address}" + (f" ({self.title})" if self.title else "")

    def clean(self):
        self.address = normalize_address(self.address)
        if not self.address:
            raise ValidationError({"address": "Нужен адрес: частота или имя сервера."})

    def save(self, *args, **kwargs):
        self.address = normalize_address(self.address)
        super().save(*args, **kwargs)


class NetNode(models.Model):
    """Страница или файл сервера по пути: info, info/attachements, info/file.pdf. Пустой путь это корень сервера.

    Текст отвечает на nreq. В тексте можно поставить {listing}: на его место встанет список того, что лежит внутри
    (папки с / на конце, затем файлы). Нет {listing}: списка нет. Текст пустой, а внутри что-то лежит: выводится только
    список. Файл отдаётся на nget: игрок получает его копию со слоями в исходном состоянии.
    """

    resource = models.ForeignKey(NetResource, on_delete=models.CASCADE, related_name="nodes")
    path = models.CharField(
        max_length=512,
        blank=True,
        help_text="Путь на сервере без начального и конечного /: info/attachements/data. Пусто это корень.",
    )
    response = models.TextField(
        blank=True,
        help_text="Ответ на nreq. {listing} вставляет список содержимого; без него списка не будет.",
    )
    item = models.ForeignKey(
        "filesystem.Item",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="net_nodes",
        help_text="Объект, который отдаёт nget по этому пути.",
    )
    key_condition = models.JSONField(
        null=True,
        blank=True,
        help_text="Без выполненного условия по ключам узла нет: ни в списке, ни по запросу.",
    )
    token = models.CharField(max_length=255, blank=True, help_text="Токен только для этого узла (--token).")

    class Meta:
        ordering = ("resource", "path")
        verbose_name = "Узел сервера"
        verbose_name_plural = "Узлы серверов"
        constraints = [models.UniqueConstraint(fields=("resource", "path"), name="unique_net_node_path")]

    def __str__(self):
        return f"{self.resource.address}/{self.path}"

    def save(self, *args, **kwargs):
        self.path = "/".join(part for part in (self.path or "").split("/") if part)
        super().save(*args, **kwargs)


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

    class Meta:
        ordering = ("code",)
        verbose_name = "Тип системы"
        verbose_name_plural = "Типы систем"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Place(models.Model):
    """Именованное место: имя и шаблон пути (secrets, desktop, trash, config, logs, temp...).

    Значения типа системы задают умолчание, машина может переопределить. Какие имена знает движок и что в них по умолчанию,
    см. machines/places.py. В шаблоне: {login} (логин записи) и {home} (место home)."""

    system_type = models.ForeignKey(SystemType, null=True, blank=True, on_delete=models.CASCADE, related_name="places")
    machine = models.ForeignKey(Machine, null=True, blank=True, on_delete=models.CASCADE, related_name="places")
    name = models.SlugField("Имя", max_length=32, help_text="home, secrets, desktop, trash, config, logs, temp или своё.")
    path = models.CharField("Путь", max_length=512, help_text="Шаблон пути: {home}/.secrets или C:\\Users\\{login}.")

    class Meta:
        ordering = ("name",)
        verbose_name = "Место"
        verbose_name_plural = "Места"
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


class MachineMount(models.Model):
    """Монтирование: машина подключает том (или его папку) в точку своей файловой системы."""

    class Mode(models.TextChoices):
        LOCAL = "local", "Локально"
        REMOTE = "remote", "По сети"

    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="mounts")
    volume = models.ForeignKey("filesystem.Volume", on_delete=models.CASCADE, related_name="mounts")
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
        return f"{self.machine.label}: {self.volume.slug} -> {self.mount_path or '(без точки)'}"

    def normalize(self):
        from filesystem.names import normalize_inner, normalize_mount

        self.volume_path = normalize_inner(self.volume_path)
        self.mount_path = normalize_mount(self.mount_path)

    def clean(self):
        super().clean()
        self.normalize()

    def save(self, *args, **kwargs):
        self.normalize()
        super().save(*args, **kwargs)
