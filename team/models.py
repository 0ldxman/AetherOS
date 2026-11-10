"""Команда авторов: роли с правами по разделам Студии (team.rights)."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from team import rights


class Role(models.Model):
    name = models.CharField("Название", max_length=64, unique=True)
    note = models.TextField("Заметка", blank=True)
    rights = models.JSONField("Права по разделам", default=dict, blank=True, help_text="{раздел: none|read|edit}")
    actions = models.JSONField("Действия", default=list, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Роль"
        verbose_name_plural = "Роли"

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        bad = [f"{section}={level}" for section, level in (self.rights or {}).items()
               if section not in rights.SECTIONS or level not in rights.LEVELS]
        if bad:
            errors["rights"] = "Неизвестные разделы или уровни: " + ", ".join(bad)
        unknown = [action for action in (self.actions or []) if action not in rights.ACTIONS]
        if unknown:
            errors["actions"] = "Неизвестные действия: " + ", ".join(unknown)
        if errors:
            raise ValidationError(errors)


class Change(models.Model):
    """Запись ленты: автор что-то изменил в Студии (team.changes). Номер записи служит версией при сохранении."""

    at = models.DateTimeField("Когда", auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="changes", verbose_name="Автор")
    username = models.CharField("Имя автора", max_length=150)            # остаётся, если автора удалят
    method = models.CharField(max_length=8)
    path = models.CharField("Путь", max_length=512, db_index=True)        # адрес сущности в API: он же ключ версии
    section = models.CharField("Раздел", max_length=32, blank=True, db_index=True)
    action = models.CharField("Действие", max_length=16)                 # create, update, delete, act
    kind = models.CharField("Вид", max_length=64, blank=True)
    label = models.CharField("Что", max_length=200, blank=True)
    link = models.CharField("Ссылка в Студии", max_length=255, blank=True)
    summary = models.CharField("Что именно", max_length=200, blank=True)
    snapshot = models.JSONField("Снимок до удаления", null=True, blank=True)

    class Meta:
        ordering = ["-pk"]
        verbose_name = "Изменение"
        verbose_name_plural = "Лента изменений"

    def __str__(self):
        return f"{self.username} {self.action} {self.path}"


class Comment(models.Model):
    """Сообщение в обсуждении сущности Студии (team.comments). Ветка: корневое сообщение и ответы на него (parent)."""

    target = models.CharField("Сущность", max_length=512, db_index=True)       # путь API, как у ленты: machines/3
    kind = models.CharField("Вид", max_length=64, blank=True)
    label = models.CharField("Что", max_length=200, blank=True)
    link = models.CharField("Ссылка в Студии", max_length=255, blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="comments")
    username = models.CharField("Имя автора", max_length=150)
    text = models.TextField("Текст")
    mentions = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="mentioned_in")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)       # у корня ветки: обсуждение решено
    resolved_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"

    def __str__(self):
        return f"{self.username}: {self.text[:40]}"


class Draft(models.Model):
    """Общий черновик сущности при совместной правке (team.collab): состояние документа Yjs комнаты.

    Мир меняет только «Сохранить» в редакторе; черновик держит несохранённое, пока его не сохранят или не отменят."""

    room = models.CharField("Комната", max_length=512, unique=True)               # путь API сущности: machines/3
    state = models.BinaryField("Состояние Yjs")
    dirty = models.BooleanField("Есть несохранённое", default=False, db_index=True)
    editors = models.JSONField("Кто правил", default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Черновик"
        verbose_name_plural = "Черновики"

    def __str__(self):
        return self.room


class Board(models.Model):
    """Доска команды (холст Excalidraw). Содержимое живёт в общем документе комнаты boards/<id> (team.collab, Draft):
    доска пишется сама, без «Сохранить», и мир от неё не меняется. Основная доска одна, её не удалить."""

    title = models.CharField("Название", max_length=120)
    main = models.BooleanField("Основная", default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="boards")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-main", "title"]
        verbose_name = "Доска"
        verbose_name_plural = "Доски"

    def __str__(self):
        return self.title

    @property
    def room(self):
        return f"boards/{self.pk}"


class Task(models.Model):
    """Задача команды (team.tasks): статус, исполнители, приоритет 1–10, срок, метки и ссылки на сущности мира."""

    class Status(models.TextChoices):
        OPEN = "open", "Открыта"
        DOING = "doing", "В работе"
        REVIEW = "review", "На проверке"
        DONE = "done", "Готово"

    title = models.CharField("Название", max_length=200)
    body = models.TextField("Описание", blank=True)
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    priority = models.PositiveSmallIntegerField("Приоритет", default=5, help_text="1–10, 10 самый высокий")
    due = models.DateField("Срок", null=True, blank=True)
    labels = models.JSONField("Метки", default=list, blank=True)
    links = models.JSONField("Сущности", default=list, blank=True, help_text="[{target, kind, label, link}]")
    assignees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_tasks")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "due", "pk"]
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"

    def __str__(self):
        return self.title


class Notification(models.Model):
    """Уведомление автору на Главной: назначили задачу, упомянули в обсуждении, срок задачи подходит или прошёл.
    key не даёт повторить одно и то же уведомление (срок напоминается один раз на задачу и день)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=16)                  # assigned, mention, due, overdue
    text = models.CharField(max_length=300)
    link = models.CharField(max_length=255, blank=True)
    key = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=("user", "key"), name="unique_notification_key")]
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"

    def __str__(self):
        return f"{self.user_id}: {self.text}"
