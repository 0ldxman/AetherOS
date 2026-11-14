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
    rotation = models.JSONField("Ротация", default=dict, blank=True, help_text="Ротация тем: {archive_days, idle_days, grace_days, volume_posts, compress_days}; ключа нет: как выше (forum/rotation.py).")
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
    rotation = models.JSONField("Ротация", default=dict, blank=True, help_text="Ротация тем: {archive_days, idle_days, grace_days, volume_posts, compress_days}; ключа нет: как выше (forum/rotation.py).")
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
    character = models.ForeignKey("characters.Character", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    pinned = models.BooleanField("Закреплена", default=False)
    locked = models.BooleanField("Закрыта", default=False, help_text="В закрытой теме отвечать нельзя.")
    created_at = models.DateTimeField(default=timezone.now)
    bumped_at = models.DateTimeField(default=timezone.now, db_index=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_reason = models.CharField(max_length=200, blank=True)
    closed_at = models.DateTimeField("Закрыта когда", null=True, blank=True)
    closed_reason = models.CharField("Почему закрыта", max_length=8, blank=True, choices=[("manual", "Вручную"), ("idle", "Неактивна"), ("volume", "Том заполнен")])
    warned_at = models.DateTimeField("Предупреждена о закрытии", null=True, blank=True)
    archived_at = models.DateTimeField("Перенесена в архив", null=True, blank=True, db_index=True)
    compressed = models.BooleanField("Сжата", default=False, help_text="В архиве остались заголовок и первое сообщение.")
    volume = models.PositiveSmallIntegerField("Том", default=0, help_text="0: тема без томов; 1, 2…: номер тома.")
    prev = models.OneToOneField("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="next", verbose_name="Предыдущий том")

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
    character = models.ForeignKey("characters.Character", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    text = models.TextField()
    useful = models.BooleanField("Полезное", default=False, help_text="Автор темы отметил ответ как полезный.")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"

    def __str__(self):
        return f"{self.name}: {self.text[:40]}"


class Attachment(models.Model):
    """Файл, приложенный к сообщению: снимок на момент отправки (ссылка на общий объект или собственное содержимое)."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="attachments")
    name = models.CharField("Имя файла", max_length=128)
    item = models.ForeignKey("filesystem.Item", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    content = models.TextField(null=True, blank=True, help_text="Своё тело: правка игрока или файл без объекта.")
    data = models.BinaryField(null=True, blank=True)
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)
        verbose_name = "Вложение"
        verbose_name_plural = "Вложения"

    def __str__(self):
        return self.name


class Reader(models.Model):
    """Когда игрок впервые открыл форум: всё, что старше, для него не «новое»."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="forum_reader")
    since = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Читатель форума"
        verbose_name_plural = "Читатели форума"


class Visit(models.Model):
    """Когда игрок последний раз открывал тему: что после этого, то для него новое."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="forum_visits")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="visits")
    seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "topic"), name="unique_forum_visit")]
        verbose_name = "Просмотр темы"
        verbose_name_plural = "Просмотры тем"
