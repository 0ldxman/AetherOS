"""Форум: пространства (сети машин), разделы дерева, темы и сообщения. Логика в forum/logic.py."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from secure.access import validate_requirements


class Kind(models.TextChoices):
    PLAYER = "player", "Игрок"
    CHARACTER = "character", "Персонаж"
    SYSTEM = "system", "Система"


class Space(models.Model):
    """Пространство: одно место общения для набора машин. Машина, к которой оно привязано, показывает его в приложении «форум»."""

    slug = models.SlugField("Адрес", max_length=48, unique=True, help_text="Короткое имя пространства: латиница, цифры, дефис.")
    title = models.CharField("Название", max_length=120)
    about = models.TextField("Описание", blank=True, help_text="Что это за место и для чего оно существует; игрок видит это в шапке.")
    machines = models.ManyToManyField("machines.Machine", blank=True, related_name="forum_spaces", verbose_name="Машины")
    read_if = models.JSONField("Кто читает", null=True, blank=True, validators=[validate_requirements],
                               help_text="Условие по ключам и меткам мира. Пусто: все, у кого машина привязана.")
    write = models.CharField("Кто пишет", max_length=8, choices=[("players", "Игроки"), ("authors", "Только авторы")], default="players")
    write_if = models.JSONField("Условие записи", null=True, blank=True, validators=[validate_requirements],
                                help_text="Дополнительное условие для игроков. Пусто: без него.")
    create = models.CharField("Кто создаёт разделы", max_length=8, choices=[("players", "Игроки"), ("authors", "Только авторы")], default="players")
    create_if = models.JSONField("Условие создания", null=True, blank=True, validators=[validate_requirements],
                                 help_text="Дополнительное условие для игроков, создающих разделы. Пусто: без него.")
    order = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "title")
        verbose_name = "Пространство"
        verbose_name_plural = "Пространства"

    def __str__(self):
        return self.title


class Section(models.Model):
    """Раздел дерева внутри пространства; правила наследуются от родителя, пока раздел не задал свои."""

    space = models.ForeignKey(Space, on_delete=models.CASCADE, related_name="sections")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    title = models.CharField("Название", max_length=120)
    about = models.CharField("Описание", max_length=240, blank=True)
    order = models.PositiveIntegerField("Порядок", default=0)
    read_if = models.JSONField("Кто читает", null=True, blank=True, validators=[validate_requirements],
                               help_text="Дополнительное условие чтения поверх родительского. Пусто: как у родителя.")
    write = models.CharField("Кто пишет", max_length=8, choices=[("inherit", "Как у родителя"), ("players", "Игроки"), ("authors", "Только авторы")], default="inherit")
    write_if = models.JSONField("Условие записи", null=True, blank=True, validators=[validate_requirements])
    create = models.CharField("Кто создаёт подразделы", max_length=8, choices=[("inherit", "Как у родителя"), ("players", "Игроки"), ("authors", "Только авторы")], default="inherit")
    create_if = models.JSONField("Условие создания", null=True, blank=True, validators=[validate_requirements])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    archived = models.BooleanField("В архиве", default=False, help_text="Раздел скрыт из списков, записи остаются.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "title")
        verbose_name = "Раздел"
        verbose_name_plural = "Разделы"

    def __str__(self):
        return self.title


class Topic(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="topics")
    title = models.CharField("Заголовок", max_length=160)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField("Подпись автора", max_length=16, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PLAYER)
    pinned = models.BooleanField("Закреплена", default=False)
    locked = models.BooleanField("Закрыта", default=False, help_text="В закрытой теме отвечать нельзя.")
    created_at = models.DateTimeField(default=timezone.now)
    bumped_at = models.DateTimeField(default=timezone.now, db_index=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-pinned", "-bumped_at")
        verbose_name = "Тема"
        verbose_name_plural = "Темы"

    def __str__(self):
        return self.title


class Post(models.Model):
    """Сообщение темы. Первое (root) это сам текст темы, остальные ответы; parent строит дерево."""

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="posts")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    root = models.BooleanField(default=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField("Подпись автора", max_length=16, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PLAYER)
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"

    def __str__(self):
        return f"{self.name}: {self.text[:40]}"
