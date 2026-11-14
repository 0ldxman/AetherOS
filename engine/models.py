"""Лента событий: что случилось в мире и с кем. Механики сообщают события через engine.events.emit; из ленты строится журнал
игрока, на неё же встанут правила."""
from django.conf import settings
from django.db import models


class Event(models.Model):
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    name = models.CharField("Событие", max_length=40, db_index=True)       # key.got, file.read, mail.sent, world.flag…
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="engine_events")
    host = models.CharField("Машина", max_length=64, blank=True)
    login = models.CharField("Учётка", max_length=64, blank=True)
    source = models.CharField("Откуда", max_length=200, blank=True)
    data = models.JSONField("Подробности", default=dict, blank=True)

    class Meta:
        ordering = ("-at", "-id")
        indexes = [models.Index(fields=("user", "-at"), name="engine_event_user_at")]
        verbose_name = "Событие"
        verbose_name_plural = "События"

    def __str__(self):
        return f"{self.name} {self.data}"
