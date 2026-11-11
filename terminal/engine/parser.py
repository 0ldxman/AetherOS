import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: list[str]


class CommandParseError(ValueError):
    pass


def _split(source, style):
    """Слова команды по правилам shell; диалект путей машины меняет, что считается служебным символом:
    в Windows обратный слэш это разделитель пути, а не экранирование; у мейнфрейма одинарные кавычки часть имени ('SYS1.X')."""
    lexer = shlex.shlex(source, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    if style == "windows":
        lexer.escape = ""
    if style == "mvs":
        lexer.quotes = '"'
    return list(lexer)


def parse_command(source: str, style: str = "unix") -> ParsedCommand | None:
    try:
        parts = _split(source, style)
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