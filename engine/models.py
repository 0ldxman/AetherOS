"""Лента событий: что случилось в мире и с кем. Механики сообщают события через engine.events.emit; из ленты строится журнал
игрока."""
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
        indexes = [models.Index(fields=("user", "-at"), name="engine_event_user_at"),
                   models.Index(fields=("user", "name", "-at"), name="engine_event_user_name_at")]
        verbose_name = "Событие"
        verbose_name_plural = "События"

    def __str__(self):
        return f"{self.name} {self.data}"


class Push(models.Model):
    """Эффект для браузера игрока вне запроса (engine/push.py): стол забирает их опросом."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    op = models.CharField(max_length=16)
    payload = models.JSONField(default=dict, blank=True)
    where = models.CharField("Где", max_length=32, blank=True, help_text="account:<номер> или machine:<номер>: показать, только когда стол "
                                                                         "(терминал — для терминальных) игрока там. Пусто — где угодно.")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    taken_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("id",)
        verbose_name = "Эффект для игрока"
        verbose_name_plural = "Эффекты для игроков"


class Value(models.Model):
    """Тег или счётчик владельца (мир, игрок, персонаж, машина, сервер, объект): общий (user пусто) или свой у игрока. Логика — engine/values.py."""

    class Kind(models.TextChoices):
        TAG = "tag", "Тег"
        COUNT = "count", "Счётчик"

    kind = models.CharField(max_length=8, choices=Kind.choices)
    owner = models.CharField("Владелец", max_length=16)           # world, player, character, machine, server, object, account
    owner_id = models.PositiveBigIntegerField("Номер вещи", default=0)    # мир — 0
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    name = models.CharField("Имя", max_length=64)
    value = models.IntegerField("Значение", default=0)              # у тега: 1 стоит, 0 снят
    changed_at = models.DateTimeField("Изменено", null=True, blank=True)
    changed_by = models.CharField("Кем", max_length=200, blank=True)

    class Meta:
        ordering = ("owner", "owner_id", "kind", "name")
        constraints = [
            models.UniqueConstraint(fields=("kind", "owner", "owner_id", "name"), condition=models.Q(user__isnull=True), name="unique_shared_value"),
            models.UniqueConstraint(fields=("kind", "owner", "owner_id", "user", "name"), condition=models.Q(user__isnull=False), name="unique_player_value_of"),
        ]
        indexes = [models.Index(fields=("owner", "owner_id", "user"), name="engine_value_owner_idx")]
        verbose_name = "Тег или счётчик"
        verbose_name_plural = "Теги и счётчики"

    def __str__(self):
        return f"{self.kind}:{self.owner}:{self.owner_id}:{self.name}={self.value}"


class ValueInfo(models.Model):
    """Описание тега или счётчика: подпись для авторов и подписи значений («2» — «Архив»). owner_id 0 — для любой вещи этого вида."""

    kind = models.CharField(max_length=8, choices=Value.Kind.choices)
    owner = models.CharField(max_length=16)
    owner_id = models.PositiveBigIntegerField(default=0)
    name = models.CharField(max_length=64)
    label = models.CharField("Подпись для авторов", max_length=200, blank=True)
    labels = models.JSONField("Подписи значений", default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("kind", "owner", "owner_id", "name"), name="unique_value_info")]
