"""Проверка внутренних путей: иконки машин и вложения писем ведут только внутрь проекта."""
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.urls import Resolver404, resolve


def validate_internal_path(value, field="path"):
    """Путь от корня сайта (например /apps/map/), существующий в проекте."""
    parts = urlsplit(value)

    if (
        parts.scheme
        or parts.netloc
        or parts.fragment
        or "\\" in value
        or not parts.path.startswith("/")
    ):
        raise ValidationError(
            {field: "Нужен внутренний путь от корня сайта, например /apps/map/."}
        )

    try:
        resolve(parts.path)
    except Resolver404:
        raise ValidationError({field: "Такого адреса нет в проекте."})
