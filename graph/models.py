"""Сценарии-графы: поведение мира, собранное из нод. Сам граф хранится одним документом (ноды и провода), а исполнение —
в прохождениях (Run), ожиданиях (Wait), отметках прохода по нодам (Hit) и счётчиках нод (Mark)."""
from django.conf import settings
from django.db import models


class Graph(models.Model):
    """Сценарий: документ {"nodes": [...], "wires": [...]}. Описание нод — graph/nodes.py."""

    slug = models.SlugField("Имя", max_length=64, unique=True)
    title = models.CharField("Название", max_length=120)
    note = models.TextField("Заметка автора", blank=True)
    active = models.BooleanField("Включён", default=False)
    doc = models.JSONField("Граф", default=dict, blank=True)
    owner = models.CharField("Принадлежит", max_length=80, blank=True, default="", db_index=True,
                             help_text="Граф попытки у вещи: «machine:12» (graph/owned.py). Пусто — обычный сценарий.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title",)
        constraints = [models.UniqueConstraint(fields=("owner",), condition=~models.Q(owner=""), name="unique_graph_owner")]
        verbose_name = "Сценарий"
        verbose_name_plural = "Сценарии"

    def __str__(self):
        return self.title


class Start(models.Model):
    """Выписка стартов графа: какая нода без входа ловит какое событие. Пересобирается при сохранении."""

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="starts")
    node = models.CharField(max_length=32)
    out = models.CharField(max_length=32)
    event = models.CharField(max_length=40, db_index=True)

    class Meta:
        verbose_name = "Старт сценария"
        verbose_name_plural = "Старты сценариев"


class Run(models.Model):
    """Прохождение: один игрок (или мир) в одном сценарии. Внутри может идти несколько веток."""

    class Status(models.TextChoices):
        RUNNING = "running", "Идёт"
        DONE = "done", "Закончено"

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="runs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="graph_runs")
    node = models.CharField("Старт", max_length=32, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.RUNNING, db_index=True)
    outcome = models.CharField("Исход", max_length=12, blank=True)
    ctx = models.JSONField("Контекст", default=dict, blank=True)          # host, login, event, data
    state = models.JSONField("Состояние", default=dict, blank=True)      # joins, races
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at", "-id")
        indexes = [models.Index(fields=("graph", "user", "status"), name="graph_run_lookup")]
        verbose_name = "Прохождение"
        verbose_name_plural = "Прохождения"


class Wait(models.Model):
    """Ветка стоит на ноде и ждёт: события (event), времени (until) или условия. Сработал один — снимаются все ожидания ноды."""

    class Kind(models.TextChoices):
        EVENT = "event", "Событие"
        TIME = "time", "Время"
        CONDITION = "condition", "Условие"

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="waits")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    node = models.CharField(max_length=32)
    out = models.CharField("Выход", max_length=32)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    event = models.CharField(max_length=40, blank=True, db_index=True)
    anyone = models.BooleanField("Событие любого игрока", default=False)
    data = models.JSONField("Значения с проводов", default=dict, blank=True)
    until = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "Ожидание"
        verbose_name_plural = "Ожидания"


class Hit(models.Model):
    """Проход через ноду: из этого счётчики на холсте и воронка этапов."""

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="hits")
    node = models.CharField(max_length=32)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    run = models.ForeignKey(Run, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("at", "id")
        indexes = [models.Index(fields=("graph", "node"), name="graph_hit_node")]
        verbose_name = "Проход ноды"
        verbose_name_plural = "Проходы нод"


class Offer(models.Model):
    """Возможность, открытая сценарием: вариант письма, скрытая команда, окно с выбором, кнопка у файла. node — нода-сущность
    «Возможность» графа; user пусто — всем, profile — всем, кто на этой учётке (разговор у учётки один). standing: «Открыть» с
    проводом условия во «Когда» (spec.by — эта нода) — открыта тем, у кого оно верно (считается при запросе)."""

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="offers")
    node = models.CharField(max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    profile = models.ForeignKey("machines.MachineProfile", null=True, blank=True, on_delete=models.CASCADE, related_name="+",
                                help_text="Для учётки: видят все, кто на ней.")
    channel = models.CharField("Канал", max_length=16, default="mail", db_index=True)
    group = models.CharField("Группа", max_length=64, blank=True)
    standing = models.BooleanField("По условию", default=False)
    spec = models.JSONField("Что предложено", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "Возможность"
        verbose_name_plural = "Возможности"


class OfferTry(models.Model):
    """Возможность «всем» или по условию, закрытая одному игроку (он её использовал или её закрыли ему)."""

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="+")
    node = models.CharField(max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    closed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("graph", "node", "user"), name="unique_offer_try")]
        verbose_name = "Закрытая игроку возможность"
        verbose_name_plural = "Закрытые игрокам возможности"


class Mark(models.Model):
    """Счётчик ноды: «по очереди», «первые в мире» (user пусто), «однажды» (на игрока), последний запуск по времени."""

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="marks")
    node = models.CharField(max_length=32)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    value = models.BigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("graph", "node", "user"), name="unique_graph_mark")]
        verbose_name = "Счётчик ноды"
        verbose_name_plural = "Счётчики нод"
