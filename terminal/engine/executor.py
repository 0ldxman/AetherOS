from terminal.engine.commands import COMMANDS
from terminal.engine.context import DEFAULT_CWD, TerminalContext
from terminal.engine.parser import (
    CommandParseError,
    parse_command,
)
from terminal.engine.result import CommandResult


class TerminalExecutor:
    def execute(
        self,
        session,
        source: str,
        cwd: str = DEFAULT_CWD,
    ) -> tuple[CommandResult, str]:
        """Выполняет команду и возвращает (результат, новая папка).

        Хранить папку между запросами должен вызывающий код,
        executor ничего не запоминает.
        """
        context = TerminalContext(
            session=session,
            cwd=cwd or DEFAULT_CWD,
        )

        try:
            parsed = parse_command(source)
        except CommandParseError as exc:
            return CommandResult(
                f"terminal: syntax error: {exc}",
                2,
            ), context.cwd

        if parsed is None:
            return CommandResult(), context.cwd

        command = COMMANDS.get(parsed.name)

        if command is None:
            return CommandResult(
                f"{parsed.name}: command not found",
                127,
            ), context.cwd

        try:
            result = command.execute(context, parsed.args)
        except Exception:
            # Не раскрываем внутренние ошибки Django пользователю.
            return CommandResult(
                "terminal: internal command error",
                1,
            ), context.cwd

        return result, context.cwd