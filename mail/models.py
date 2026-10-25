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
        help_text="Простой текст. Абзацы и переносы строк сохраняются.",
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
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    label = models.CharField("Подпись", max_length=128)

    path = models.CharField(
        "Путь",
        max_length=512,
        help_text="Внутренний путь от корня сайта, например /apps/wiki/.",
    )

    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("message", "order", "id")

    def __str__(self):
        return self.label

    def clean(self):
        validate_internal_path(self.path)


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
