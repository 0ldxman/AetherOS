from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from secure.access import validate_requirements


def validate_no_colon(value):
    # двоеточие разделяет путь в ссылках: Технологии:Оружие:Название
    if ":" in value:
        raise ValidationError("Двоеточие в названии запрещено: оно разделяет путь.")


class Namespace(models.Model):
    MAX_DEPTH = 4
    RESERVED_ROOT_NAMES = {"go", "search"}

    name = models.CharField(max_length=100, validators=[validate_no_colon])
    # короткий id подключения (показывается в списке баз); пусто = без id
    slug = models.SlugField(max_length=50, blank=True, default="")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    # показывается ли раздел в списках; формат см. secure/access.py, пусто = всем
    visibility = models.JSONField(
        default=dict, blank=True, validators=[validate_requirements]
    )
    # открыт ли раздел; пусто = всем
    access = models.JSONField(
        default=dict, blank=True, validators=[validate_requirements]
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            # в PostgreSQL NULL считаются разными, поэтому корневые
            # неймспейсы проверяем отдельным ограничением
            models.UniqueConstraint(
                fields=["parent", "name"],
                name="wiki_namespace_unique_in_parent",
            ),
            models.UniqueConstraint(
                fields=["name"],
                condition=Q(parent__isnull=True),
                name="wiki_namespace_unique_root",
            ),
            models.UniqueConstraint(
                fields=["slug"],
                condition=~Q(slug=""),
                name="wiki_namespace_unique_slug",
            ),
        ]

    def __str__(self):
        return self.path()

    def chain(self):
        """Цепочка от корня до этого неймспейса включительно."""
        nodes = []
        node = self
        while node is not None:
            nodes.append(node)
            node = node.parent
        return nodes[::-1]

    def path(self):
        return ":".join(n.name for n in self.chain())

    def clean(self):
        super().clean()
        seen = {self.pk} if self.pk else set()
        depth = 1
        node = self.parent
        while node is not None:
            if node.pk in seen:
                raise ValidationError({"parent": "Родитель создаёт цикл."})
            seen.add(node.pk)
            depth += 1
            node = node.parent
        if depth > self.MAX_DEPTH:
            raise ValidationError(
                {"parent": f"Максимальная вложенность: {self.MAX_DEPTH}."}
            )
        if self.parent is None and self.name in self.RESERVED_ROOT_NAMES:
            raise ValidationError({"name": "Это имя зарезервировано."})
        if Document.objects.filter(namespace=self.parent, title=self.name).exists():
            raise ValidationError(
                {"name": "Рядом уже есть запись с таким названием."}
            )


class Document(models.Model):
    class Type(models.TextChoices):
        DOC = "doc", "Документ"
        SCAN = "scan", "Скан"
        WEB = "web", "Веб-снапшот"

    EXTENSIONS = {"doc": ".doc", "scan": ".scan", "web": ".snapshot"}

    namespace = models.ForeignKey(
        Namespace,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documents",
    )

    title = models.CharField(max_length=200, validators=[validate_no_colon])
    type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.DOC
    )
    body = models.TextField(blank=True)  # markdown
    infobox = models.TextField(blank=True)  # markdown

    direct_link = models.SlugField(
        max_length=100, blank=True, default="", validators=[validate_no_colon]
    )

    # показывается ли запись в списках и поиске; формат см. secure/access.py
    visibility = models.JSONField(
        default=dict, blank=True, validators=[validate_requirements]
    )
    # открыта ли запись; пусто = открыто всем
    access = models.JSONField(
        default=dict, blank=True, validators=[validate_requirements]
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["namespace", "title"],
                name="wiki_document_unique_in_namespace",
            ),
            # записи без неймспейса (в корне)
            models.UniqueConstraint(
                fields=["title"],
                condition=Q(namespace__isnull=True),
                name="wiki_document_unique_root",
            ),
            models.UniqueConstraint(
                fields=["direct_link"],
                condition=~Q(direct_link=""),
                name="wiki_document_unique_direct_link",
            )
        ]

    def __str__(self):
        return self.path()

    def path(self):
        parts = [n.name for n in self.namespace.chain()] if self.namespace else []
        return ":".join(parts + [self.title])
    
    def clean(self):
        super().clean()
        if Namespace.objects.filter(parent=self.namespace, name=self.title).exists():
            raise ValidationError(
                {"title": "Рядом уже есть раздел с таким названием."}
            )
    
    @property
    def ext(self):
        return self.EXTENSIONS.get(self.type, "")