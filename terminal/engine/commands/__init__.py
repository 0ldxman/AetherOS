from terminal.engine.commands.basic import (
    CdCommand,
    ClearCommand,
    LsCommand,
    PwdCommand,
)
from terminal.engine.commands.bridge import (
    BridgeCloseCommand, BridgeCommand, ExitCommand, MntCommand, RshellCommand, UmntCommand, XferCommand,
)
from terminal.engine.commands.archive import PakCommand
from terminal.engine.commands.crypto import WardCommand
from terminal.engine.commands.info import CntCommand, EdtCommand, FtypCommand
from terminal.engine.commands.net import NgetCommand, NreqCommand
from terminal.engine.commands.files import Cp, Mv
from terminal.engine.commands.inspect import TxtxCommand
from terminal.engine.commands.help import HelpCommand
from terminal.engine.commands.keys import KexCommand
from terminal.engine.commands.trash import Del, Rcvr, Wipe
from terminal.engine.commands.raw import BlkCommand, CvtCommand, RprCommand
from terminal.engine.commands.rights import OwnCommand, PermCommand
from terminal.engine.commands.system import DateCommand, TmsetCommand

# Общие для всех систем команды файловой системы.
COMMON = (
    HelpCommand,
    PwdCommand,
    LsCommand,
    CdCommand,
    ClearCommand,
    FtypCommand,
    WardCommand,
    PakCommand,
    TxtxCommand,
    KexCommand,
    BlkCommand,
    CvtCommand,
    RprCommand,
    NreqCommand,
    NgetCommand,
    Del,
    Rcvr,
    Wipe,
    Mv,
    Cp,
    CntCommand,
    EdtCommand,
    PermCommand,
    OwnCommand,
    DateCommand,
    TmsetCommand,
)

# У каждой системы свой набор и свои названия команд: у Aether мост это rcon, rcon-close и exit,
# у других систем это будут свои (например ssh и logout). Нового вида систем достаточно добавить сюда.
COMMANDS_BY_SYSTEM = {
    "AETHER": {
        command.name: command()
        for command in (*COMMON, BridgeCommand, RshellCommand, XferCommand, BridgeCloseCommand, ExitCommand, MntCommand, UmntCommand)
    },
}

DEFAULT_SYSTEM = "AETHER"


def commands_for(system):
    """Команды системы машины; незнакомая система получает набор Aether."""
    return COMMANDS_BY_SYSTEM.get(system) or COMMANDS_BY_SYSTEM[DEFAULT_SYSTEM]


COMMANDS = COMMANDS_BY_SYSTEM[DEFAULT_SYSTEM]
