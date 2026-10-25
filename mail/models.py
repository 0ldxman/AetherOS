"""Почта узла («intercom»): письма, вложения и кто что прочитал.

Письма пишет автор в админке, игрок их читает. Кому письмо видно, решают три вещи:
машина (или все машины), адресат (логин на машине или все) и условие по ключам,
как у иконок и записей вики. Прочитанность своя у каждого игрока.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from machines.paths import validate_internal_path


class Message(models.Model):
    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mail",
        help_text="Пусто: письмо видно на всех машинах.",
    )

    to_login = models.CharField(
        "Адресат",
        max_length=128,
        blank=True,
        help_text="Логин на машине (например witness). Пусто: всем.",
    )

    sender_login = models.CharField(
        "Логин отправителя",
        max_length=128,
        blank=True,
        help_text=(
            "Чей это ящик в «отправленных» или «черновиках» (логин на этой машине). "
            "Пусто для писем со стороны и от системы."
        ),
    )

    is_draft = models.BooleanField(
        "Черновик",
        default=False,
        help_text="Неотправленное письмо: лежит в «черновиках» логина отправителя.",
    )

    status_note = models.CharField(
        "Пометка",
        max_length=255,
        blank=True,
        help_text="Системная строка над текстом, например: not sent: system fault 0x2a.",
    )

    slug = models.SlugField(
        "Идентификатор",
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        help_text="Нужен для доставки по триггеру: действие хука «mail <идентификатор>».",
    )

    class Delivery(models.TextChoices):
        OPEN = "open", "По правилам (видно сразу)"
        TRIGGER = "trigger", "Только после доставки (триггер)"

    delivery = models.CharField(
        "Доставка",
        max_length=8,
        choices=Delivery.choices,
        default=Delivery.OPEN,
        help_text="«Только после доставки»: письмо появляется у игрока, когда сработает хук mail.",
    )

    sender_name = models.CharField(
        "От кого",
        max_length=128,
        help_text="Как подписан отправитель. Можно замазать: ██████.",
    )

    sender_address = models.CharField(
        "Адрес отправителя",
        max_length=255,
        blank=True,
        help_text="Например ██████@aether-core.",
    )

    subject = models.CharField(
        "Тема",
        max_length=255,
        blank=True,
    )

    body = models.TextField(
        "Текст",
        blank=True,
        help_text=(
            "Простой текст. Абзацы сохраняются. Можно: # заголовок, ## подзаголовок, "
            "- пункт списка, > цитата, **жирный**, *курсив*, `код`."
        ),
    )

    label = models.CharField(
        "Метка",
        max_length=32,
        blank=True,
        help_text="Короткий ярлык на карточке и в боковой панели, например system или personal.",
    )

    class Tone(models.TextChoices):
        DIM = "dim", "Серая"
        INFO = "info", "Голубая"
        OK = "ok", "Зелёная"
        WARN = "warn", "Жёлтая"
        ERROR = "error", "Красная"

    label_tone = models.CharField(
        "Цвет метки",
        max_length=8,
        choices=Tone.choices,
        default=Tone.DIM,
    )

    sent_at = models.DateTimeField(
        "Отправлено",
        help_text="Время в мире игры: когда письмо «пришло».",
    )

    key_condition = models.JSONField(
        "Условие по ключам",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-sent_at", "-id")

    def __str__(self):
        return f"{self.subject or '(no subject)'} ({self.sender_name})"


class Attachment(models.Model):
    """Вложение письма. Три вида:

    link   внутренняя ссылка (запись вики и т.п.): открыть в окне;
    asset  файл из хранилища (Nextcloud): открыть во вьювере и скачать на ПК;
    file   файл машины: сохранить его в файловую систему игрока (нужен вход через Discord).
    """

    class Kind(models.TextChoices):
        LINK = "link", "Ссылка"
        ASSET = "asset", "Файл из хранилища"
        FILE = "file", "Файл на машину"

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.LINK)

    label = models.CharField("Подпись", max_length=128)

    path = models.CharField(
        "Путь",
        max_length=512,
        blank=True,
        help_text="Для ссылки: внутренний путь от корня сайта, например /apps/wiki/.",
    )

    asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mail_attachments",
        help_text="Для файла из хранилища.",
    )

    machine_file = models.ForeignKey(
        "filesystem.MachineFile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mail_attachments",
        help_text="Для файла на машину. Лучше отметить его «delivered only», чтобы он не лежал у всех.",
    )

    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("message", "order", "id")

    def __str__(self):
        return self.label

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.kind == self.Kind.LINK:
            if not self.path:
                raise ValidationError({"path": "Для ссылки нужен путь."})
            validate_internal_path(self.path)
        elif self.kind == self.Kind.ASSET and self.asset_id is None:
            raise ValidationError({"asset": "Выберите файл из хранилища."})
        elif self.kind == self.Kind.FILE and self.machine_file_id is None:
            raise ValidationError({"machine_file": "Выберите файл машины."})


class MessageRead(models.Model):
    """Игрок прочитал письмо. Вошедший игрок отмечается по пользователю, безымянный (witness) по сессии."""

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="reads",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mail_reads",
    )

    session_key = models.CharField(max_length=64, blank=True)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("message", "user"),
                condition=Q(user__isnull=False),
                name="unique_mail_read_per_user",
            ),
            models.UniqueConstraint(
                fields=("message", "session_key"),
                condition=~Q(session_key=""),
                name="unique_mail_read_per_session",
            ),
            models.CheckConstraint(
                condition=Q(user__isnull=False) | ~Q(session_key=""),
                name="mail_read_has_a_reader",
            ),
        ]

    def __str__(self):
        return f"{self.message_id} read by {self.user_id or self.session_key[:8]}"


class Delivered(models.Model):
    """Письмо по триггеру доставлено игроку (с задержкой: оно появится в available_at)."""

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mail_deliveries",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    available_at = models.DateTimeField(help_text="С этого момента игрок видит письмо.")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("message", "user"), name="unique_mail_delivery"),
        ]
        verbose_name_plural = "deliveries"

    def __str__(self):
        return f"{self.message_id} -> {self.user_id} at {self.available_at:%Y-%m-%d %H:%M:%S}"
