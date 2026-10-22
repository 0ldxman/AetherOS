from terminal.engine.commands.basic import (
    CdCommand,
    LsCommand,
    PwdCommand,
)
from terminal.engine.commands.crypto import B256Command, CphCommand
from terminal.engine.commands.info import FtypCommand
from terminal.engine.commands.raw import RprCommand


COMMANDS = {
    command.name: command()
    for command in (
        PwdCommand,
        LsCommand,
        CdCommand,
        FtypCommand,
        CphCommand,
        B256Command,
        RprCommand,
    )
}