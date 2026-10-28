"""Что открывается, когда игрок открывает файл машины (cnt в терминале, вложение в почте).

Сначала ответ верхнего слоя на cnt. Если его нет и блокирующих слоёв не осталось, открывается
MachineFile.url: какое окно соответствует адресу, знает его вид содержимого (filesystem/sources).
Прогресс сессии (снятые слои) учитывается, если у игрока есть запись SessionFile.
"""
from filesystem.sources import Content, resolve_window
from filesystem.states.attempt import top_answer
from filesystem.states.compiler import compile_text
from filesystem.states.registry import registry
from filesystem.states.stack import build_stack, load_progress

COMMAND = "cnt"


def resolve_content(machine_file, session_file, path, name):
    """Адрес содержимого файла или причина, почему его нельзя открыть."""
    canonical_text = machine_file.state or ""
    raw_state = session_file.state if session_file else ""

    url_path = top_answer(canonical_text, raw_state, COMMAND, path=path, name=name, only_top=True)

    if url_path is None:
        canonical = compile_text(canonical_text, registry) if canonical_text.strip() else []
        stack = build_stack(canonical, load_progress(raw_state, canonical_text), registry)

        if stack:
            return Content(error="locked")

        url_path = machine_file.url

    return resolve_window(url_path, path)
