import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: list[str]


class CommandParseError(ValueError):
    pass


def parse_command(source: str) -> ParsedCommand | None:
    try:
        parts = shlex.split(source)
    except ValueError as exc:
        raise CommandParseError(str(exc)) from exc

    if not parts:
        return None

    if any(part in {"|", "||", "&&", ";", ">", ">>", "<"} for part in parts):
        raise CommandParseError(
            "Shell operators are not supported."
        )

    return ParsedCommand(
        name=parts[0],
        args=parts[1:],
    )