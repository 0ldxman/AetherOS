from filesystem.trash import purge_expired
from machines.world.dialect import PathSyntax
from terminal.engine.commands import commands_for
from terminal.engine.context import DEFAULT_CWD, TerminalContext
from terminal.engine.parser import (
    CommandParseError,
    parse_command,
)
from filesystem import rights
from filesystem.machine_view import BadName, Occupied, ReadOnly
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
            parsed = parse_command(source, context.style)
        except CommandParseError as exc:
            return CommandResult(
                f"terminal: syntax error: {exc}",
                2,
            ), context.cwd

        if parsed is None:
            return CommandResult(), context.cwd

        command = commands_for(context.machine.system).get(parsed.name)

        if command is None:
            from terminal.engine import offers as hidden

            found = hidden.run(session, context, parsed)
            if found is not None:
                return found, context.cwd
            return CommandResult(
                f"{parsed.name}: command not found",
                127,
            ), context.cwd

        from engine.events import emit, heard

        if heard("command.run"):
            emit("command.run", session.user, machine=context.machine, login=getattr(context.view, "login", "") or "",
                 command=parsed.name, args=" ".join(parsed.args)[:300])
        return guarded(parsed.name, context, lambda: command.execute(context, parsed.args)), context.cwd


def guarded(name, context, call):
    """Выполнить call() команды name: ошибки файловой системы — ответом терминала, внутренние — общим текстом (с записью в лог).
    Нужен и командам, которые доделывают работу после вопроса (del, wipe)."""
    try:
        return call()
    except PathSyntax as bad:
        return CommandResult(f"{name}: {bad}", 2)
    except rights.Denied as denied:
        return CommandResult(f"{name}: {context.show(denied.path)}: Permission denied", 1)
    except rights.NotPermitted:
        return CommandResult(f"{name}: Operation not permitted", 1)
    except BadName as bad:
        return CommandResult(f"{name}: {bad}: Invalid argument", 1)
    except ReadOnly as where:
        return CommandResult(f"{name}: {where}: Read-only file system", 1)
    except Occupied as where:
        return CommandResult(f"{name}: {where}: Device or resource busy", 1)
    except Exception:
        import logging

        logging.getLogger("terminal").exception("command failed: %s", name)
        return CommandResult("terminal: internal command error", 1)          # внутренние ошибки Django игроку не раскрываем