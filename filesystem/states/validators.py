"""Валидатор поля со стеком слоёв (MachineFile.state) для админки."""

from django.core.exceptions import ValidationError

from filesystem.states.compiler import StateError, compile_text


def validate_state_text(value):
    """Показывает админу все ошибки сразу, каждая с номером строки."""
    if not value or not value.strip():
        return

    try:
        compile_text(value)
    except StateError as exc:
        raise ValidationError([str(p) for p in exc.problems]) from exc