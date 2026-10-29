import re

from django.core.exceptions import ValidationError
from django.db import models


LISTING_TAG = "{listing}"


SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*)://", re.I)


def normalize_address(text):
    """Адрес сервера как его хранят и ищут: схема (если есть) и имя строчными, без пути, запроса и конечных слэшей.
    https://Apollo.com/info/ -> https://apollo.com; apollo.com остаётся apollo.com (сервер для любой схемы)."""
    scheme, host, _ = split_url(text)
    return f"{scheme}://{host}" if scheme and host else host


def split_url(text):
    """(схема, адрес, путь) из того, что набрал игрок: https://apollo.com/info/ -> ("https", "apollo.com", "info").
    Схемы может не быть: тогда это пустая строка."""
    text = (text or "").strip()
    found = SCHEME.match(text)
    scheme = found.group(1).lower() if found else ""
    text = SCHEME.sub("", text, count=1)
    text = re.split(r"[?#]", text, maxsplit=1)[0]
    host, _, path = text.partition("/")
    return scheme, host.strip().lower(), "/".join(part for part in path.split("/") if part)


class NetResource(models.Model):
    """Сетевой ресурс: «сервер», к которому обращаются командами nreq и nget (внутриигровой, реальной сети нет).

    Адрес это частота у Aether или имя сервера (apollo.com) у остальных систем. Что на сервере лежит, описывают его
    узлы (NetNode): страницы с текстом и файлы по путям, как на сайте.
    """

    address = models.CharField(
        max_length=255,
        unique=True,
        help_text=(
            "Что вводит игрок: частота (14.230) или имя сервера (apollo.com). Регистр не важен. "
            "Со схемой (ftp://apollo.com) игрок должен набрать её; без схемы сервер отвечает на любую."
        ),
    )
    title = models.CharField(max_length=128, blank=True, help_text="Название для админки; игрок его не видит.")
    key_condition = models.JSONField(
        null=True,
        blank=True,
        help_text="Без выполненного условия по ключам сервер не находится: игроку он отвечает как несуществующий.",
    )
    token = models.CharField(
        max_length=255,
        blank=True,
        help_text="Если задан, сервер отвечает только тому, кто назвал его в --token. Без него: 401.",
    )

    class Meta:
        ordering = ("address",)
        verbose_name = "Сетевой ресурс"
        verbose_name_plural = "Сетевые ресурсы"

    def __str__(self):
        return f"{self.address}" + (f" ({self.title})" if self.title else "")

    def clean(self):
        self.address = normalize_address(self.address)
        if not self.address:
            raise ValidationError({"address": "Нужен адрес: частота или имя сервера."})

    def save(self, *args, **kwargs):
        self.address = normalize_address(self.address)
        super().save(*args, **kwargs)


class NetNode(models.Model):
    """Страница или файл сервера по пути: info, info/attachements, info/file.pdf. Пустой путь это корень сервера.

    Текст отвечает на nreq. В тексте можно поставить {listing}: на его место встанет список того, что лежит внутри
    (папки с / на конце, затем файлы). Нет {listing}: списка нет. Текст пустой, а внутри что-то лежит: выводится только
    список. Файл отдаётся на nget: игрок получает его копию со слоями в исходном состоянии.
    """

    resource = models.ForeignKey(NetResource, on_delete=models.CASCADE, related_name="nodes")
    path = models.CharField(
        max_length=512,
        blank=True,
        help_text="Путь на сервере без начального и конечного /: info/attachements/data. Пусто это корень.",
    )
    response = models.TextField(
        blank=True,
        help_text="Ответ на nreq. {listing} вставляет список содержимого; без него списка не будет.",
    )
    item = models.ForeignKey(
        "filesystem.Item",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="net_nodes",
        help_text="Объект, который отдаёт nget по этому пути.",
    )
    key_condition = models.JSONField(
        null=True,
        blank=True,
        help_text="Без выполненного условия по ключам узла нет: ни в списке, ни по запросу.",
    )
    token = models.CharField(max_length=255, blank=True, help_text="Токен только для этого узла (--token).")

    class Meta:
        ordering = ("resource", "path")
        verbose_name = "Узел сервера"
        verbose_name_plural = "Узлы серверов"
        constraints = [models.UniqueConstraint(fields=("resource", "path"), name="unique_net_node_path")]

    def __str__(self):
        return f"{self.resource.address}/{self.path}"

    def save(self, *args, **kwargs):
        self.path = "/".join(part for part in (self.path or "").split("/") if part)
        super().save(*args, **kwargs)
