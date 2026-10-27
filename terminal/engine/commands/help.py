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
        "list the commands or explain one",
        ("help", "help <command>"),
        "Without arguments lists every command of this system. With a command name shows its usage and what it does.",
    ),
    "pwd": ("print the current directory", ("pwd",), ""),
    "ls": (
        "list a directory",
        ("ls [-a] [-l] [-h] [path]",),
        "-a also shows hidden names (starting with a dot), -l shows sizes in bytes, -h makes them human readable.\n"
        "An archive is listed as one file.",
    ),
    "cd": (
        "change the current directory",
        ("cd [path]",),
        "Archives are files, not folders: unpack them with pak x before looking inside.",
    ),
    "clear": ("clear the screen", ("clear",), ""),
    "cnt": (
        "open a file",
        ("cnt <file>", "cnt -r <file>"),
        "Opens the file in its viewer. -r opens the raw byte viewer (hex and text) instead and works for every file.\n"
        "A file under a layer (password, damage, encoding...) cannot be opened until the layer is removed.\n"
        "Archives and pieces cut with blk have no viewer: read them with cnt -r.",
    ),
    "ftyp": (
        "tell what kind of file this is",
        ("ftyp <file>",),
        "The top layer of the file answers first. Without a layer the start of the file decides "
        "(PDF document, REC record, PGP encrypted data...), otherwise it is just data.",
    ),
    "txtx": (
        "print readable strings from the bytes of a file",
        ("txtx <file>",),
        "Prints runs of printable characters with their offsets (0x...). These offsets are what blk and kex ask for.",
    ),
    "rpr": (
        "repair a damaged file",
        ("rpr <file>",),
        "Rebuilds the damaged blocks. A file can be damaged more than once: repair it again while it still needs it.",
    ),
    "cvt": (
        "read a file as its real format or decode its text encoding",
        ("cvt ext <file> <out.ext>", "cvt ext <file> .ext", "cvt enc <encoding> <file>"),
        "ext: a file that pretends to be something else is read as the format of the extension. With a full output name "
        "a copy is made, with only an extension (.pdf) the file itself is converted and renamed.\n"
        "enc: removes a text encoding (utf16, cp1251, rot13, base64, gzip, morse, hex...).\n"
        "A wrong guess shows the real first bytes of the file.",
    ),
    "blk": (
        "cut a piece of a file into a new file (like dd)",
        ("blk <file> skip=N [count=M]", "blk <file> start=A [end=B]"),
        "skip and count are 512-byte blocks, start and end are byte addresses (end is not included). Without count or "
        "end the cut runs to the end of the file.\n"
        "The result is a new file next to the source, named <name>.prt.<start in hex>. If the piece starts exactly where "
        "the real data of a shifted file begins, you get the real file instead, under the name its layer gives it.\n"
        "The source never changes. Look at the result with ftyp and cnt -r.",
    ),
    "kex": (
        "extract a key found in the bytes of a file",
        ("kex <file> <offset>",),
        "Reads the file as you see it now. If a key block (-----BEGIN ACCESS KEY-----) starts at the offset, the key is "
        "saved to /home/.secrets/<keyname>. The offset is decimal or 0x hex, as printed by txtx.\n"
        "example: kex dump.img 0x4d",
    ),
    "ward": (
        "decrypt files, check and make signatures",
        (
            "ward <file> <password>", "ward -k <keyname> <file>", "ward keys",
            "ward verify [<signature>] <file>", "ward sign -k <keyname> <file>",
        ),
        "Decrypts a file with a password or with a key from /home/.secrets (ward keys lists them with their IDs).\n"
        "verify checks the signatures inside a file, or a signature file (.sig) against another file: Good, BAD or none.\n"
        "sign makes <file>.sig with a key you hold. Archives have their own password: pak pass.",
    ),
    "pak": (
        "work with archives",
        ("pak l <archive>", "pak x <archive> [member...] [-d dir]", "pak pass <archive> <password>"),
        "An archive is a file that holds other files. l shows them as a tree, x unpacks all or the named members next to "
        "the archive (or into -d dir), pass takes off the archive password.\n"
        "A nested archive opens only after the outer one is unpacked. A damaged or password-protected archive cannot be read.",
    ),
    "mv": ("move or rename files", ("mv <source>... <destination>",), "Does not overwrite: delete the target first."),
    "cp": (
        "copy files",
        ("cp [-r] <source>... <destination>",),
        "-r copies folders. A copy keeps the layers of the original. Does not overwrite.",
    ),
    "del": (
        "move files to the trash",
        ("del [-f] [-r] <file>...",),
        "Asks before deleting, -f skips the question, -r takes folders. System files cannot be deleted. "
        "The trash is /trash and keeps things for a week.",
    ),
    "rcvr": (
        "take a file back from the trash",
        ("rcvr <file-in-trash> [destination]",),
        "The longer a file lay in the trash, the more damaged it comes back.",
    ),
    "wipe": ("empty the trash for good", ("wipe [-f]",), ""),
    "nreq": (
        "send a request to a network address",
        ("nreq [--token <token>] <address>[/path]",),
        "Prints what the server answers. Some addresses ask for a token.",
    ),
    "nget": (
        "download a file from a network address",
        ("nget [--token <token>] [-o <path>] <address>/<path/to/file>",),
        "The file arrives in your session with its layers, under its own name or -o path.",
    ),
    "rcon": (
        "log in to another machine (the desktop switches)",
        ("rcon [-p <freq>] [-i <keyname>] [--token <token>] <login>@<host>",),
        "-i names a key from /home/.secrets, -p picks the endpoint when a login is served on several. "
        "exit goes one level back, rcon-close closes everything.",
    ),
    "rshell": (
        "log in to another machine inside the terminal",
        ("rshell [-p <freq>] [-i <keyname>] [--token <token>] <login>@<host>",),
        "Like rcon, but the desktop stays where it is. exit goes back.",
    ),
    "xfer": (
        "move a file between machines",
        ("xfer :<remote path> <local path>", "xfer <local path> :<remote path>",
         "xfer [-p <freq>] [-i <keyname>] [--token <token>] <login>@<host>:<path> <local path>"),
        "Inside rshell a path with a leading colon is on the remote machine. With an address no rshell is needed.",
    ),
    "exit": ("go back one level after rcon or rshell", ("exit",), ""),
    "rcon-close": ("close every open session", ("rcon-close",), ""),
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
