"""Почта узла («intercom»): письма, вложения и кто что прочитал.

У письма есть отправитель, получатели, название, содержание, дата и статус. Ящик это адрес
профиля (MachineProfile.mail): игрок, вошедший под профилем, видит письма этого адреса.
Прочитанность своя у каждого игрока, корзина своя у каждого профиля.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from machines.paths import validate_internal_path

from mail.addresses import split, validate_address, validate_masks


class Message(models.Model):
    sender = models.CharField(
        "Отправитель",
        max_length=255,
        validators=[validate_address],
        help_text="Адрес, например commander@neweden.mail. Можно замазать: ██████@aether-core.",
    )

    recipients = models.TextField(
        "Получатели",
        blank=True,
        validators=[validate_masks],
        help_text=(
            "Адреса по одному в строку. «*» заменяет любые символы: *@aether-* это все ящики "
            "на aether-main и aether-null, просто * это все."
        ),
    )

    class Status(models.TextChoices):
        OK = "ok", "Отправлено"
        DRAFT = "draft", "Черновик"

    status = models.CharField(
        "Статус",
        max_length=8,
        choices=Status.choices,
        default=Status.OK,
        help_text="Черновик лежит в черновиках отправителя и никому не приходит.",
    )

    subject = models.CharField(
        "Название",
        max_length=255,
        blank=True,
    )

    body = models.TextField(
        "Содержание",
        blank=True,
        help_text=(
            "Простой текст. Абзацы сохраняются. Можно: # заголовок, ## подзаголовок, "
            "- пункт списка, > цитата, **жирный**, *курсив*, `код`."
        ),
    )

    sent_at = models.DateTimeField(
        "Дата",
        help_text="Время в мире игры: когда письмо «пришло».",
    )

    slug = models.SlugField(
        "Идентификатор",
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        help_text=(
            "Необязательно. Если задан, письмо придёт игроку только когда сработает действие "
            "хука «mail <идентификатор>». Пусто: письмо видно сразу."
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

    key_condition = models.JSONField(
        "Условие по ключам",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-sent_at", "-id")
        indexes = [
            models.Index(fields=["sender"], name="mail_message_sender_idx"),
            models.Index(fields=["-sent_at", "-id"], name="mail_message_sent_idx"),
        ]

    def __str__(self):
        return f"{self.subject or '(no subject)'} ({self.sender})"

    @property
    def is_trigger(self):
        return bool(self.slug)

    @property
    def is_draft(self):
        return self.status == self.Status.DRAFT


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

    item = models.ForeignKey(
        "filesystem.Item",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mail_attachments",
        help_text="Для файла на машину: объект, который игрок может сохранить к себе.",
    )

    save_path = models.CharField(
        "Куда сохранить",
        max_length=512,
        blank=True,
        help_text="Путь на машине игрока (или имя файла в его домашней папке). Пусто: домашняя папка, под именем объекта.",
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
        elif self.kind == self.Kind.FILE and self.item_id is None:
            raise ValidationError({"item": "Выберите объект."})


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


class Trashed(models.Model):
    """Письмо лежит в корзине профиля: персонаж его «удалил», игрок под этим профилем найдёт его там."""

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="trashed",
    )

    profile = models.ForeignKey(
        "machines.MachineProfile",
        on_delete=models.CASCADE,
        related_name="trashed_mail",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("message", "profile"), name="unique_mail_trashed"),
        ]
        verbose_name = "письмо в корзине"
        verbose_name_plural = "корзина профилей"

    def __str__(self):
        return f"{self.message_id} in {self.profile_id}"


class ComposeTask(models.Model):
    """Задача на набор: игрок, вошедший под чужим логином, должен написать письмо «от его лица».

    Целевой текст виден бледным слоем; набранные буквы закрашиваются, ошибочная подсвечивается
    красным. Часть текста можно скрыть: {{secret}} показывается только числом символов, игрок
    должен знать само значение (найденный пароль, имя). После верной отправки письмо остаётся в
    «отправленных» игрока, а ответные письма приходят с задержкой.
    """

    profile = models.ForeignKey(
        "machines.MachineProfile",
        on_delete=models.CASCADE,
        related_name="compose_tasks",
        verbose_name="От чьего имени",
        help_text="Профиль, под которым игрок должен быть вошёл: письмо уйдёт с его адреса.",
    )

    recipients = models.TextField(
        "Кому",
        validators=[validate_masks],
        help_text="Адреса получателей по одному в строку.",
    )

    subject = models.CharField("Название", max_length=255, blank=True)

    target = models.TextField(
        "Целевой текст",
        help_text="Что нужно набрать. Скрытое пишется в двойных фигурных скобках: пароль {{hunter2}}.",
    )

    key_condition = models.JSONField("Условие по ключам", null=True, blank=True)

    max_attempts = models.PositiveSmallIntegerField(
        "Попыток отправить",
        default=5,
        help_text="Сколько раз игрок может отправить неверный текст (ошибка в скрытой части). 0: без ограничения.",
    )

    reply_delay = models.PositiveIntegerField(
        "Задержка ответа, с",
        default=30,
        help_text="Через сколько секунд после отправки придут ответные письма.",
    )

    replies = models.ManyToManyField(
        Message,
        blank=True,
        related_name="reply_to_tasks",
        limit_choices_to={"slug__isnull": False},
        help_text="Ответные письма (только с идентификатором: они приходят по доставке).",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("profile", "id")

    def __str__(self):
        return f"{self.profile.mail} -> {', '.join(split(self.recipients))}: {self.subject or '(no subject)'}"


class ComposeProgress(models.Model):
    """Что сделал игрок с задачей на набор: неверные отправки и когда отправил."""

    task = models.ForeignKey(ComposeTask, on_delete=models.CASCADE, related_name="progress")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mail_tasks")
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    text = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("task", "user"), name="unique_compose_progress"),
        ]
        verbose_name_plural = "compose progress"

    def __str__(self):
        return f"{self.task_id} / {self.user_id}: {'sent' if self.sent_at else f'{self.attempts} failed'}"
