"""Почта на файлах (mail.boxes): письма лежат в ящиках учёток на машинах, здесь только состояние игрока.

MailMark: прочитано ли письмо и когда оно пришло (для доставленных); своё у каждого игрока (гость witness: по сессии).
MailQueue: письма, которые придут игроку позже (задержка исхода или хука).
"""
from django.conf import settings
from django.db import models


class MailMark(models.Model):
    machine = models.ForeignKey("machines.Machine", on_delete=models.CASCADE, related_name="mail_marks")
    path = models.CharField("Путь письма", max_length=1024)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="mail_marks")
    session_key = models.CharField(max_length=64, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True, help_text="Время машины игрока, когда письмо пришло.")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("machine", "path", "user", "session_key"), name="unique_mail_mark")]
        indexes = [models.Index(fields=("user", "machine"), name="mailmark_user_machine_idx")]
        verbose_name = "Отметка письма"
        verbose_name_plural = "Отметки писем"

    def __str__(self):
        return f"{self.path} ({self.user_id or self.session_key[:8]})"


class MailQueue(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mail_queue")
    profile = models.ForeignKey("machines.MachineProfile", on_delete=models.CASCADE, related_name="mail_queue")
    item = models.ForeignKey("filesystem.Item", on_delete=models.CASCADE, related_name="mail_queue")
    folder = models.CharField(max_length=16, default="inbox")
    available_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("available_at", "pk")
        verbose_name = "Письмо в очереди"
        verbose_name_plural = "Очередь писем"

    def __str__(self):
        return f"{self.item_id} -> {self.user_id} at {self.available_at:%Y-%m-%d %H:%M:%S}"
