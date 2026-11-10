"""Форматы файлов и кодировки как таблицы автора: правка с теми же проверками, что в админке, переименование с объектами,
удаление только неиспользуемого. API Студии это обёртка над этими функциями."""
from django.db import transaction

from filesystem.admin.forms import FileEncodingForm, FileFormatForm, part_errors
from filesystem.content.rawview.registry import invalidate
from filesystem.models import FileEncoding, FileFormat, FormatPart, Item, ItemRevision

FORMAT_FIELDS = ("name", "title", "extension", "aliases", "kind", "magic", "template", "content", "markup", "editable")


class FormatError(Exception):
    """Ошибки по полям: {"поле": ["сообщение"]}; «__all__» это ошибка всей записи."""

    def __init__(self, errors):
        super().__init__(str(errors))
        self.errors = errors


def used(name):
    """Сколько объектов имеют этот формат."""
    return Item.objects.filter(format=name).count()


def counts():
    from django.db.models import Count

    return dict(Item.objects.exclude(format="").values_list("format").annotate(n=Count("id")))


@transaction.atomic
def save_format(instance, data, parts):
    """Создать или изменить формат с частями (parts: список {name, source, value}, порядок по списку). Переименование меняет формат у
    всех объектов и версий. FormatError, если что-то не так."""
    before = instance.name if instance is not None else None
    form = FileFormatForm({key: data[key] for key in FORMAT_FIELDS if key in data}, instance=instance)
    errors = {key: [str(m) for m in messages] for key, messages in form.errors.items()}
    kind = data.get("kind", "")
    if kind in ("chunks", "package", "zip") and not parts and not errors:
        errors["parts"] = ["Для блоков и пакета нужна хотя бы одна часть."]
    for index, part in enumerate(parts, 1):
        for field, message in part_errors(kind, part["name"], part["source"], part.get("value", "")):
            errors.setdefault("parts", []).append(f"Часть {index}, {field}: {message}")
    if errors:
        raise FormatError(errors)
    saved = form.save()
    if before and before != saved.name:
        Item.objects.filter(format=before).update(format=saved.name)
        ItemRevision.objects.filter(format=before).update(format=saved.name)
    saved.parts.all().delete()
    FormatPart.objects.bulk_create([
        FormatPart(format=saved, order=index, name=part["name"], source=part["source"], value=part.get("value", "")) for index, part in enumerate(parts)
    ])
    invalidate()
    return saved


@transaction.atomic
def delete_format(instance):
    """Удалить формат, которого нет ни у одного объекта."""
    count = used(instance.name)
    if count:
        raise FormatError({"__all__": [f"Формат «{instance.name}» у объектов: {count}. Сначала смените им формат."]})
    instance.delete()
    invalidate()


@transaction.atomic
def save_encoding(instance, data):
    form = FileEncodingForm({key: data[key] for key in ("name", "title", "kind", "param") if key in data}, instance=instance)
    if not form.is_valid():
        raise FormatError({key: [str(m) for m in messages] for key, messages in form.errors.items()})
    saved = form.save()
    invalidate()
    return saved


def delete_encoding(instance):
    instance.delete()
    invalidate()
