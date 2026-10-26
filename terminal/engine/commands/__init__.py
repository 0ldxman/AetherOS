from terminal.engine.commands.basic import (
    CdCommand,
    ClearCommand,
    LsCommand,
    PwdCommand,
)
from terminal.engine.commands.bridge import BridgeCloseCommand, BridgeCommand, ExitCommand
from terminal.engine.commands.crypto import B256Command, CphCommand
from terminal.engine.commands.info import FtypCommand, CntCommand
from terminal.engine.commands.raw import RprCommand

# Общие для всех систем команды файловой системы.
COMMON = (
    PwdCommand,
    LsCommand,
    CdCommand,
    ClearCommand,
    FtypCommand,
    CphCommand,
    B256Command,
    RprCommand,
    CntCommand,
)

# У каждой системы свой набор и свои названия команд: у Aether мост это bridge, bridge-close и exit,
# у других систем это будут свои (например ssh и logout). Нового вида систем достаточно добавить сюда.
COMMANDS_BY_SYSTEM = {
    "AETHER": {
        command.name: command()
        for command in (*COMMON, BridgeCommand, BridgeCloseCommand, ExitCommand)
    },
}

DEFAULT_SYSTEM = "AETHER"


def commands_for(system):
    """Команды системы машины; незнакомая система получает набор Aether."""
    return COMMANDS_BY_SYSTEM.get(system) or COMMANDS_BY_SYSTEM[DEFAULT_SYSTEM]


COMMANDS = COMMANDS_BY_SYSTEM[DEFAULT_SYSTEM]
