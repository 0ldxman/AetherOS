from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    output: str = ""
    exit_code: int = 0
    window: dict | None = None  # {"id": ..., "title": ..., "url": ...}
    # консольная сцена (шаги scenes/engine.py), которая проигрывается ДО текста ответа: работа команды.
    # Текст output остаётся ответом и печатается после неё, так что без анимации ничего не теряется.
    scene: list | None = None
    clear: bool = False         # очистить экран терминала (команда clear)
    # что браузер делает после ответа, по порядку: {"op": "switch"} перезагрузить рабочий стол (машина сменилась),
    # {"op": "lock", "url"} на экран входа, {"op": "play", "scene"} доиграть сцену, {"op": "alert", ...} окна ошибок
    effects: list | None = None
    # запрос дополнительного ввода: {"kind": "password", "text": "login@host's password: "}; ответ приходит отдельным запросом
    prompt: dict | None = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0
