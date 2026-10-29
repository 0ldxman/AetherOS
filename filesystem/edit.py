"""Правка текста файла (edt): какие файлы можно править и как правка ложится в слой игрока.

Правится текст файла: тело объекта (в слое игрока ложится его своя версия, объект и база не меняются) или собственный текст файла
игрока. Нельзя править ассеты, ссылки, карты, письма, ключи и форматы без флага «можно править». Слои защиты не снимаются: закрытый
слоями файл сначала открывают.
"""
from filesystem.models import KEY_FORMAT
from filesystem.content.rawview import registry


def refusal(entry):
    """Почему файл нельзя править (текст причины) или None."""
    if entry.is_dir:
        return "Is a directory"
    item = entry.item
    if item is None:
        return None if entry.own_text is not None else "not a text file"
    if item.asset_id or item.url or item.scene_id or item.message_id or item.format == KEY_FORMAT or entry.archive:
        return "not a text file"
    if item.format:
        found = registry.format_named(item.format)
        if found is None or not found.editable:
            return "this format cannot be edited"
    return None
