"""Персонаж мира: одно лицо во всех каналах (почта, эфир, форум) и карточка для авторов, чтобы держать один голос."""
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class Character(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        SILENT = "silent", "Молчит"
        MISSING = "missing", "Пропал"
        DEAD = "dead", "Мёртв"

    code = models.CharField("Код", max_length=3, unique=True, validators=[RegexValidator(r"^[A-Z0-9]{3}$", "Три знака: латинские буквы и цифры.")],
                            help_text="Бейдж отправителя на форуме и в ленте кукловода: OP7, SYS, MAP.")
    name = models.CharField("Имя", max_length=120, help_text="Как персонажа зовут в мире.")
    callsign = models.CharField("Позывной", max_length=16, blank=True, help_text="Подпись в эфире и на форуме. Пусто: имя.")
    color = models.PositiveSmallIntegerField("Цвет кода", default=0, help_text="0 акцент, 1 зелёный, 2 предупреждение, 3 сведения (токены ОС).")
    status = models.CharField("Статус", max_length=8, choices=Status.choices, default=Status.ACTIVE)
    about = models.TextField("Кто это", blank=True)
    voice = models.TextField("Как говорит", blank=True, help_text="Манера, слова-паразиты, чего никогда не скажет.")
    knows = models.TextField("Что знает", blank=True, help_text="И чего не знает: чтобы не проговориться.")
    note = models.TextField("Заметка", blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="characters",
                              verbose_name="Ведёт", help_text="Автор, которому идут входящие персонажа. Пусто: всем.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Персонаж"
        verbose_name_plural = "Персонажи"

    def __str__(self):
        return f"{self.code} {self.name}"

    @property
    def signature(self):
        """Как персонаж подписан на форуме и в эфире."""
        return self.callsign or self.name


class Inbound(models.Model):
    """Что игрок написал персонажу вне сценариев: письмо на его адрес, ответ или упоминание на форуме, позывной в эфире."""

    class Channel(models.TextChoices):
        MAIL = "mail", "Почта"
        FORUM = "forum", "Форум"
        AIR = "air", "Эфир"

    class Status(models.TextChoices):
        NEW = "new", "Новое"
        TAKEN = "taken", "Взято"
        ANSWERED = "answered", "Отвечено"
        SKIPPED = "skipped", "Пропущено"

    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="inbound")
    channel = models.CharField(max_length=8, choices=Channel.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    sender = models.CharField("От кого", max_length=255, help_text="Адрес, позывной или логин отправителя, как его видит мир.")
    subject = models.CharField("Тема", max_length=255, blank=True)
    text = models.TextField(blank=True)
    ref = models.JSONField("Где лежит", default=dict, blank=True, help_text="mail: machine, path; forum: topic, post; air: transmission, freq.")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.NEW, db_index=True)
    taken_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    taken_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("character", "channel", "status"), name="inbound_char_channel_idx")]
        verbose_name = "Входящее персонажа"
        verbose_name_plural = "Входящие персонажей"

    def __str__(self):
        return f"{self.character.code} {self.channel}: {self.text[:40]}"
