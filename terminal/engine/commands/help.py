"""help: список команд системы и справка по каждой.

Тексты лежат здесь одним словарём: HELP[имя] = (одна строка, строки синтаксиса, пояснение). Команда, которой нет в словаре,
в справке без текста, а тест не даст добавить команду без справки. Показываются только команды, которые есть у системы машины.
"""
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.result import CommandResult

# порядок и группы в списке help
GROUPS = (
    ("files", ("ls", "cd", "pwd", "cnt", "mv", "cp", "del", "rcvr", "wipe", "clear")),
    ("inspect and repair", ("ftyp", "txtx", "rpr", "cvt", "blk")),
    ("keys and archives", ("kex", "ward", "pak")),
    ("network", ("nreq", "nget", "rcon", "rshell", "xfer", "exit", "rcon-close")),
    ("other", ("help",)),
)

HELP = {
    "help": (
        "list the available commands or show how to use one",
        ("help", "help <command>"),
        "Without arguments lists every command of this system. With a command name shows its usage.",
    ),
    "pwd": ("print the working directory", ("pwd",), ""),
    "ls": (
        "list directory contents",
        ("ls [-a] [-l] [-h] [path]",),
        "-a  do not hide entries whose names start with a dot\n"
        "-l  show sizes in bytes\n"
        "-h  with -l, print sizes in human readable form",
    ),
    "cd": ("change the working directory", ("cd [path]",), ""),
    "clear": ("clear the terminal screen", ("clear",), ""),
    "cnt": (
        "open a file",
        ("cnt <file>", "cnt -r <file>"),
        "Opens the file in the viewer that suits it.\n"
        "-r  show the raw contents of the file as hexadecimal and text instead",
    ),
    "ftyp": (
        "determine the type of a file",
        ("ftyp <file>",),
        "Examines the beginning of the file and reports what it looks like, the way file(1) does.",
    ),
    "txtx": (
        "print the printable strings of a file",
        ("txtx <file>",),
        "Prints every run of at least four printable characters together with its offset in the file, like strings -t x.",
    ),
    "rpr": (
        "repair a damaged file",
        ("rpr <file>",),
        "Rebuilds unreadable blocks from the data that remains. If errors remain, run it again.",
    ),
    "cvt": (
        "convert a file between formats or text encodings",
        ("cvt ext <file> <out.ext>", "cvt ext <file> .ext", "cvt enc <encoding> <file>"),
        "ext  read the file as the format of the given extension. With a full output name the result is written there, "
        "with only an extension (.pdf) the file itself is converted and renamed.\n"
        "enc  decode the text of the file from the named encoding (utf16, cp1251, rot13, base64, gzip, morse, hex...)",
    ),
    "blk": (
        "copy a piece of a file into a new file (like dd)",
        ("blk <file> skip=N [count=M]", "blk <file> start=A [end=B]"),
        "skip and count are in 512-byte blocks. start and end are byte addresses, end is not included.\n"
        "Without count or end the copy runs to the end of the file.\n"
        "The piece is written next to the input as <name>.prt.<start in hex>; a piece that identifies itself "
        "may be named after what it is. The input is not modified.",
    ),
    "kex": (
        "import a key from the bytes of a file",
        ("kex <file> <offset>",),
        "Reads the file at the given offset and imports the key block found there (-----BEGIN ACCESS KEY-----) "
        "into the key store /home/.secrets/<keyname>.\n"
        "The offset is decimal or 0x hexadecimal, like the ones txtx prints.",
    ),
    "ward": (
        "decrypt files, verify and make signatures",
        (
            "ward <file> <password>", "ward -k <keyname> <file>", "ward keys",
            "ward verify [<signature>] <file>", "ward sign -k <keyname> <file>",
        ),
        "<file> <password>  decrypt with a passphrase\n"
        "-k <keyname>       decrypt with a key from /home/.secrets\n"
        "keys               list the keys in /home/.secrets with their IDs\n"
        "verify             check the signatures inside a file, or a detached signature (.sig) against a file\n"
        "sign               write <file>.sig, signed with a key you hold\n"
        "Archives are not handled here, see pak.",
    ),
    "pak": (
        "list and extract archives",
        ("pak l <archive>", "pak x <archive> [member...] [-d dir]", "pak pass <archive> <password>"),
        "l     list the contents as a tree\n"
        "x     extract everything, or the named members, into a directory next to the archive (or into -d dir)\n"
        "pass  remove the password protection of an archive\n"
        "A damaged or password-protected archive cannot be read.",
    ),
    "mv": ("move or rename files", ("mv <source>... <destination>",), "Refuses to overwrite an existing file."),
    "cp": (
        "copy files",
        ("cp [-r] <source>... <destination>",),
        "-r  copy directories recursively\nRefuses to overwrite an existing file.",
    ),
    "del": (
        "move files to the trash",
        ("del [-f] [-r] <file>...",),
        "Asks for confirmation, -f does not. -r removes directories. Protected system files cannot be removed.\n"
        "Files in /trash are purged after seven days.",
    ),
    "rcvr": (
        "restore a file from the trash",
        ("rcvr <file-in-trash> [destination]",),
        "Files that have stayed in the trash may not come back intact.",
    ),
    "wipe": ("empty the trash permanently", ("wipe [-f]",), "Asks for confirmation, -f does not."),
    "nreq": (
        "send a request to a network address",
        ("nreq [--token <token>] <address>[/path]",),
        "Prints the answer of the server. Some addresses require a token.",
    ),
    "nget": (
        "download a file from a network address",
        ("nget [--token <token>] [-o <path>] <address>/<path/to/file>",),
        "-o  where to save the file (default: its own name in the working directory)",
    ),
    "rcon": (
        "open a remote console on another machine",
        ("rcon [-p <freq>] [-i <keyname>] [--token <token>] <login>@<host>",),
        "-p  endpoint (frequency) when the login is served on several\n"
        "-i  key from /home/.secrets to present\n"
        "exit returns one level, rcon-close closes every session.",
    ),
    "rshell": (
        "open a shell on another machine inside this terminal",
        ("rshell [-p <freq>] [-i <keyname>] [--token <token>] <login>@<host>",),
        "Takes the same options as rcon. exit returns to the previous shell.",
    ),
    "xfer": (
        "copy a file between machines",
        ("xfer :<remote path> <local path>", "xfer <local path> :<remote path>",
         "xfer [-p <freq>] [-i <keyname>] [--token <token>] <login>@<host>:<path> <local path>"),
        "Inside an rshell session a path with a leading colon is on the remote machine. "
        "With a login@host address no session is needed.",
    ),
    "exit": ("leave the current remote session", ("exit",), ""),
    "rcon-close": ("close every open remote session", ("rcon-close",), ""),
}


def known(command):
    """Тексты справки для имени команды или None."""
    return HELP.get(command)


class HelpCommand(BaseCommand):
    name = "help"

    def execute(self, context, args):
        from terminal.engine.commands import commands_for

        available = commands_for(context.machine.system)
        if len(args) > 1:
            return CommandResult("usage: help [command]", 2)
        if args:
            return self.one(args[0], available)
        return self.listing(available)

    def listing(self, available):
        shown, lines = set(), []
        width = max((len(name) for name in available), default=4)
        for title, names in GROUPS:
            rows = [name for name in names if name in available]
            if not rows:
                continue
            lines += ["", f"{title}:"]
            for name in rows:
                shown.add(name)
                lines.append(f"  {name:<{width}}  {HELP.get(name, ('', (), ''))[0]}".rstrip())
        rest = [name for name in sorted(available) if name not in shown]
        if rest:
            lines += ["", "more:"] + [f"  {name:<{width}}  {HELP.get(name, ('', (), ''))[0]}".rstrip() for name in rest]
        lines += ["", "help <command> shows the usage of a command."]
        return CommandResult("\n".join(lines).lstrip("\n"), 0)

    def one(self, name, available):
        if name not in available:
            return CommandResult(f"help: no such command '{name}'", 1)
        text = HELP.get(name)
        if text is None:
            return CommandResult(f"help: no help for '{name}'", 1)
        summary, synopsis, details = text
        lines = [f"{name}: {summary}", "", "usage:", *(f"  {line}" for line in synopsis)]
        if details:
            lines += ["", *details.splitlines()]
        return CommandResult("\n".join(lines), 0)
