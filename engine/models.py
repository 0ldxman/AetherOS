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


class Rule(models.Model):
    """Правило: когда случилось событие (и подробности подходят), а у игрока выполнено условие, выполнить действия."""

    class Once(models.TextChoices):
        WORLD = "world", "Один раз в мире"
        PLAYER = "player", "Раз на игрока"
        ALWAYS = "always", "Каждый раз"

    name = models.SlugField("Имя", max_length=64, unique=True)
    label = models.CharField("Подпись для авторов", max_length=200, blank=True)
    on = models.CharField("Событие", max_length=40, db_index=True)
    match = models.JSONField("Подробности", default=dict, blank=True, help_text="{поле: значение}; в значении * — любые знаки.")
    condition = models.JSONField("Условие", null=True, blank=True, help_text="На факты игрока: ключи, flag:, world:.")
    actions = models.JSONField("Действия", default=list, blank=True)
    once = models.CharField("Сколько раз", max_length=8, choices=Once.choices, default=Once.PLAYER)
    active = models.BooleanField("Включено", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Правило"
        verbose_name_plural = "Правила"

    def __str__(self):
        return self.name


class RuleFire(models.Model):
    """Срабатывание правила: кто и когда. Первое срабатывание правила — «кто первым»."""

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, related_name="fires")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("at", "id")
        verbose_name = "Срабатывание правила"
        verbose_name_plural = "Срабатывания правил"
