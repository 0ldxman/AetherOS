from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    output: str = ""
    exit_code: int = 0
    window: dict | None = None  # {"id": ..., "title": ..., "url": ...}
    # консольная сцена (шаги console/scene.py), которая проигрывается ДО текста ответа: работа команды.
    # Текст output остаётся ответом и печатается после неё, так что без анимации ничего не теряется.
    scene: list | None = None
    clear: bool = False         # очистить экран терминала (команда clear)

    @property
    def success(self) -> bool:
        return self.exit_code == 0
