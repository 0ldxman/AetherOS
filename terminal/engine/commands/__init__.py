from terminal.engine.commands.basic import (
    CdCommand,
    LsCommand,
    PwdCommand,
)


COMMANDS = {
    command.name: command()
    for command in (
        PwdCommand,
        LsCommand,
        CdCommand,
    )
}