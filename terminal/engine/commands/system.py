"""date и tmset: время машины. Часы свои у игрока на каждой машине (machines/clock.py), двигает их запись с привилегией clock."""
from machines import clock
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.result import CommandResult


class DateCommand(BaseCommand):
    name = "date"

    def execute(self, context, args):
        if args:
            return CommandResult("usage: date", 2)
        return CommandResult(clock.now(context.machine, context.user).strftime("%a %b %e %H:%M:%S %Y"))


class TmsetCommand(BaseCommand):
    """tmset <время>: поставить часы машины. +3h, -1d, +30m сдвигают, 2026-11-02 10:30 ставит точное время, reset возвращает мировое."""

    name = "tmset"
    usage = "usage: tmset +3h | -1d | YYYY-MM-DD [HH:MM[:SS]] | reset"

    def execute(self, context, args):
        if not args:
            return CommandResult(self.usage, 2)
        context.need("clock")
        offset = clock.parse(" ".join(args), context.machine, context.user)
        if offset is None:
            return CommandResult(f"tmset: invalid time: {' '.join(args)}\n{self.usage}", 2)
        clock.set_offset(context.machine, context.user, offset)
        return CommandResult(clock.now(context.machine, context.user).strftime("%a %b %e %H:%M:%S %Y"))
