from filesystem.trash import purge_expired
from terminal.engine.commands import commands_for
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
        request=None,
    ) -> tuple[CommandResult, str]:
        """Выполняет команду и возвращает (результат, новая папка).

        Хранить папку между запросами должен вызывающий код,
        executor ничего не запоминает.
        """
        context = TerminalContext(
            session=session,
            cwd=cwd or DEFAULT_CWD,
            request=request,
        )

        purge_expired(session.user)     # срок файлов в корзине вышел: они удаляются насовсем

        try:
            parsed = parse_command(source)
        except CommandParseError as exc:
            return CommandResult(
                f"terminal: syntax error: {exc}",
                2,
            ), context.cwd

        if parsed is None:
            return CommandResult(), context.cwd

        command = commands_for(context.machine.system).get(parsed.name)

        if command is None:
            return CommandResult(
                f"{parsed.name}: command not found",
                127,
            ), context.cwd

        try:
            result = command.execute(context, parsed.args)
        except Exception:
            import logging

            logging.getLogger("terminal").exception("command failed: %s", parsed.name)
            # Не раскрываем внутренние ошибки Django пользователю.
            return CommandResult(
                "terminal: internal command error",
                1,
            ), context.cwd

        return result, context.cwd