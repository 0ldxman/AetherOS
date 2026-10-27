"""Что открывается, когда игрок открывает файл машины (cnt в терминале, вложение в почте).

Сначала ответ верхнего слоя на cnt. Если его нет и блокирующих слоёв не осталось, открывается
MachineFile.url. Прогресс сессии (снятые слои) учитывается, если у игрока есть запись SessionFile.
"""
from dataclasses import dataclass

from django.urls import get_script_prefix

from filesystem.states.attempt import top_answer
from filesystem.states.compiler import compile_text
from filesystem.states.registry import registry
from filesystem.states.stack import build_stack, load_progress

COMMAND = "cnt"


@dataclass
class Content:
    url: str = ""
    error: str = ""     # "locked" | "empty" | "bad_path"


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

    if not url_path or not url_path.strip() or url_path.strip() == "slice" or url_path.strip().startswith("keys/"):
        return Content(error="empty")                 # вырезки и ключи игрока: адреса у них нет, читаются как байты (cnt -r)

    url_path = url_path.strip()

    # только внутренние пути сайта
    if "://" in url_path or url_path.startswith("//") or "\\" in url_path or url_path.startswith("/"):
        return Content(error="bad_path")

    return Content(url=get_script_prefix().rstrip("/") + "/" + url_path)
