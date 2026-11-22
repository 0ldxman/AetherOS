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
    panel = models.JSONField("Раскладка пульта", default=list, blank=True,
                             help_text="Порядок и ширина плиток пульта на странице сценария: [{node, w} | {title}]. Нод, которых тут нет, ставятся в конец.")
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
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children",
                               help_text="Ветка «Ожидания веток» или «Ответвить»: поток, который её запустил.")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                              help_text="Владелец потока: двигают его только его действия. Пусто (и без группы) — любой игрок.")
    crew = models.ForeignKey("Crew", null=True, blank=True, on_delete=models.SET_NULL, related_name="runs",
                             help_text="Группа инициаторов — владелец потока: его двигает любой из группы.")

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
    """Счётчик ноды: «Направить: По очереди» (общий на мир, user пусто) и последний запуск по времени («Время», «Расписание»)."""

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="marks")
    node = models.CharField(max_length=32)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    value = models.BigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("graph", "node", "user"), name="unique_graph_mark")]
        verbose_name = "Счётчик ноды"
        verbose_name_plural = "Счётчики нод"


class Crew(models.Model):
    """Группа инициаторов: именованный состав игроков сценария. Состав живой: нода «Группа инициаторов» добавляет, убирает, закрывает
    и открывает вступление из любого места графа. Группа — владелец потока: его двигает любой из неё."""

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="crews")
    name = models.CharField("Имя", max_length=64)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="+", blank=True)
    closed = models.BooleanField("Закрыта для вступления", default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("graph", "name"), name="unique_graph_crew")]
        verbose_name = "Группа инициаторов"
        verbose_name_plural = "Группы инициаторов"

    def __str__(self):
        return self.name


class Branching(models.Model):
    """Набор «Ветвления» с повтором: открыт ли он, сколько веток уже занято и кем. Свободная ветка (вакансия) — обычный Run
    с state.vacancy; занята она, когда сработал её первый триггер."""

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="branchings")
    node = models.CharField(max_length=64)
    open = models.BooleanField("Открыт", default=True)
    taken = models.PositiveIntegerField("Занято веток", default=0)
    users = models.JSONField("Сколько веток у игрока", default=dict, blank=True)     # {номер игрока: веток}
    base = models.JSONField("Данные новой ветки", default=dict, blank=True)         # данные потока на входе в ветвление: их получает каждая новая ветка

    class Meta:
        constraints = [models.UniqueConstraint(fields=("graph", "node"), name="unique_graph_branching")]
        verbose_name = "Набор ветвления"
        verbose_name_plural = "Наборы ветвлений"


class Entry(models.Model):
    """Журнал сценария: что и когда произошло (кто нажал, какой этап пройден, чья ветка занята). Пишется рантаймом (graph/journal.py)."""

    graph = models.ForeignKey(Graph, on_delete=models.CASCADE, related_name="journal")
    kind = models.CharField("Вид", max_length=12)
    text = models.CharField("Что произошло", max_length=300)
    who = models.CharField("Кто", max_length=80, blank=True)
    node = models.CharField(max_length=64, blank=True)
    run = models.PositiveIntegerField("Поток", null=True, blank=True)            # без связи: потоки стираются при сбросе, а журнал остаётся
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-id",)
        indexes = [models.Index(fields=("graph", "-id"), name="graph_entry_graph")]
        verbose_name = "Запись журнала"
        verbose_name_plural = "Журнал сценариев"


class Shared(models.Model):
    """Переменные сценария: один общий словарь «путь → значение» на сценарий (ноды «Переменная: …»). Живёт, пока есть сценарий."""

    graph = models.OneToOneField(Graph, on_delete=models.CASCADE, related_name="shared")
    data = models.JSONField("Переменные", default=dict, blank=True)

    class Meta:
        verbose_name = "Переменные сценария"
        verbose_name_plural = "Переменные сценариев"
