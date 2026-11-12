"""at: что запланировано в мире (видимые игрокам моменты, world/moments.py), со временем машины и обратным отсчётом."""
from machines.world import chrono
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.result import CommandResult


class AtCommand(BaseCommand):
    name = "at"
    usage = "usage: at"

    def execute(self, context, args):
        from world import moments

        if args:
            return CommandResult(self.usage, 2)
        request = getattr(context, "request", None)
        keys = frozenset()
        if request is not None:
            from secure.requestkeys import request_keys

            keys = request_keys(request)
        rows = moments.board(context.machine, getattr(context, "profile", None), keys)
        if not rows:
            return CommandResult("no jobs scheduled")
        game = chrono.game_now()
        lines = []
        for row in rows:
            if row["state"] == "live":
                lines.append(f"{'now':<20}  {row['title']:<24}  ends in {moments.countdown((row['end'] - game).total_seconds())}")
            else:
                when = chrono.in_zone(row["start"], context.machine).strftime("%Y-%m-%d %H:%M %Z")
                lines.append(f"{when:<20}  {row['title']:<24}  in {moments.countdown((row['start'] - game).total_seconds())}")
        return CommandResult("\n".join(lines))
