"""Что открывается, когда игрок открывает файл (cnt в терминале, вложение в почте).

Сначала ответ верхнего слоя на cnt. Если его нет и блокирующих слоёв не осталось, открывается окно по виду содержимого файла
(filesystem/content/sources): ассет во вьювере, карта и письмо в своих приложениях, ссылка по адресу, текст простым окном.
Прогресс игрока (снятые слои) учитывается.
"""
from filesystem.content.sources import Content, page_window, window_for
from filesystem.layers.attempt import top_answer
from filesystem.layers.compiler import compile_text
from filesystem.layers.registry import registry
from filesystem.layers.stack import build_stack, load_progress

COMMAND = "cnt"


def resolve_content(entry, path, name):
    """Окно файла или причина, почему его нельзя открыть."""
    canonical_text = entry.state or ""
    answer = top_answer(canonical_text, entry.progress, COMMAND, path=path, name=name, only_top=True)

    if answer is not None:
        return page_window(answer)

    canonical = compile_text(canonical_text, registry) if canonical_text.strip() else []
    if build_stack(canonical, load_progress(entry.progress, canonical_text), registry):
        return Content(error="locked")

    return window_for(entry)
