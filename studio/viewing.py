"""Объект глазами вьювера: ссылка ?item=<id> для сотрудников, чтобы открыть объект так, как его увидит игрок.

Вьювер (документ и другие) ищет файл по параметру запроса (filesystem.content.locate). Студия добавляет свой: объект
берётся сам по себе, без места и без условий тома и папок. Условие самого объекта и слои работают как у игрока.
"""
from filesystem.machine_view.entries import Entry
from filesystem.models import Item


def locate_item(request, value):
    user = getattr(request, "user", None)
    if user is None or not user.is_staff or not value.isdigit():
        return None
    item = Item.objects.filter(pk=int(value)).first()
    if item is None:
        return None
    return Entry(path="/" + item.default_filename, item=item), None


def view_url(item):
    """Ссылка на вьювер объекта (без выбора ключей) или None, если у формата нет вьювера-документа."""
    from documents.views import page_url

    found = item.file_format()
    return page_url({"item": item.pk}) if found is not None and found.markup else None
