"""Техподдержка: обращения игроков к команде и переписка по ним (вне мира игры)."""
from django.conf import settings
from django.db import models


class Ticket(models.Model):
    class Category(models.TextChoices):
        BUG = "bug", "Ошибка"
        STUCK = "stuck", "Застрял"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        NEW = "new", "Новое"
        OPEN = "open", "В работе"
        WAITING = "waiting", "Ждёт игрока"
        CLOSED = "closed", "Закрыто"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tickets")
    subject = models.CharField("Тема", max_length=200)
    category = models.CharField(max_length=8, choices=Category.choices, default=Category.OTHER)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.NEW, db_index=True)
    responder = models.CharField("Кто отвечает игроку", max_length=60, blank=True,
                                 help_text="Имя, которым подписаны все ответы команды в этом обращении (для игрока это ИИ узла). Пусто: общее имя.")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_tickets")
    context = models.JSONField("Где был игрок", default=dict, blank=True)
    player_seen_at = models.DateTimeField(null=True, blank=True, help_text="Когда игрок последний раз открыл обращение.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ("-updated_at", "-pk")
        verbose_name = "Обращение"
        verbose_name_plural = "Обращения"

    def __str__(self):
        return f"#{self.pk} {self.subject}"


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    staff = models.BooleanField(default=False, help_text="Ответ команды (иначе игрока).")
    internal = models.BooleanField(default=False, help_text="Заметка команды: игрок её не видит.")
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")


class TicketFile(models.Model):
    """Вложение сообщения: байты в базе (как файлы игроков), картинки показываются прямо в переписке."""

    message = models.ForeignKey(TicketMessage, on_delete=models.CASCADE, related_name="files")
    name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    data = models.BinaryField()

    @property
    def is_image(self):
        return self.content_type in IMAGE_TYPES


IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
