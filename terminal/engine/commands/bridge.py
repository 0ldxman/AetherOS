"""Команды входа на другую машину: rcon (войти с переключением рабочего стола), rshell (войти только в терминале),
xfer (перенести файл между машинами), exit (на уровень выше), rcon-close (закрыть всё).

Условия входа и стеки сессий в machines/bridge.py. Здесь разбор команды, имя ключа из папки секретов (-i), запрос пароля
и ответы в духе ssh. Отказ не говорит, какое условие не выполнено: только перечень способов записи,
Permission denied (publickey,password). Нет машины или записи называется прямо.

Три команды входят одинаково (одни и те же условия, сцены и отказы) и различаются только тем, что делают с принятой
записью: rcon открывает мост и меняет рабочий стол, rshell вкладывает оболочку в терминал, xfer переносит файл.
"""
from filesystem import keystore
from machines import bridge
from terminal import bridge_scenes as scenes
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.context import DEFAULT_CWD, TerminalContext
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult
from terminal.engine.transfer import copy_file

PENDING_KEY = "bridge_pending"
SWITCH = [{"op": "switch"}]


def _denied(profile, system, host, endpoint=None):
    listed = ",".join(bridge.methods(profile)) or "none"
    return CommandResult(
        f"Permission denied ({listed}).", 1, scene=scenes.denied_scene(system, host, profile.login, endpoint)
    )


def answer_prompt(request, text, session, cwd):
    """Ответ на запрос пароля. Возвращает (результат, папка после ответа)."""
    from machines.models import MachineProfile

    pending = request.session.pop(PENDING_KEY, None) or {}
    profile = MachineProfile.objects.filter(pk=pending.get("profile")).select_related("machine").first()
    command = ENTRY_COMMANDS.get(pending.get("mode"))
    context = TerminalContext(session=session, cwd=cwd, request=request)
    if profile is None or command is None:
        return CommandResult(), cwd

    if pending["key_ok"] and bridge.password_ok(profile, text):
        return command().finish(context, profile, pending.get("args") or {}), context.cwd

    return _denied(profile, profile.machine.system, profile.machine.hostname, f"{profile.freq:.3f} MHz"), cwd


class EntryCommand(BaseCommand):
    """Общая часть rcon, rshell и xfer: разбор -p, -i (имя ключа из /home/.secrets), --token, поиск записи и проверка условий входа."""

    mode = ""

    def execute(self, context, args):
        request = context.request
        if request is None or not request.user.is_authenticated:
            return CommandResult(f"{self.name}: not available here", 1)

        opts = self._parse(args)
        if isinstance(opts, str):
            return CommandResult(opts, 2)

        request.session.pop(PENDING_KEY, None)
        return self.run(context, opts)

    def run(self, context, opts):
        raise NotImplementedError

    def finish(self, context, profile, args):
        """Условия выполнены: что делает команда с принятой записью."""
        raise NotImplementedError

    def enter(self, context, opts, target, args=None):
        """Проверка входа на target (login@host). Возвращает CommandResult (отказ, ошибка, запрос пароля) или результат finish."""
        request = context.request
        args = args or {}
        login, _, host = target.partition("@")
        if not login or not host:
            return CommandResult(self.usage, 2)

        endpoint = None
        if opts["endpoint"] is not None:
            endpoint = bridge.parse_endpoint(opts["endpoint"])
            if endpoint is None:
                return CommandResult(f"{self.name}: bad endpoint '{opts['endpoint']}'", 2)

        slugs = set()
        for path in opts["keys"]:
            found = self._read_key(context, path)
            if isinstance(found, str):
                return CommandResult(found, 1)
            slugs |= found

        found = bridge.resolve(host, login, endpoint)
        system = context.machine.system
        if found.error == "no_host":
            return CommandResult(
                f"{self.name}: could not resolve host '{host}'", 1, scene=scenes.unreachable_scene(system, host)
            )
        if found.error == "no_account":
            return CommandResult(
                f"{self.name}: no such account '{login}' on {host}", 1,
                scene=scenes.denied_scene(system, host, login),
            )
        if found.error == "ambiguous":
            return CommandResult(f"{self.name}: '{login}' is served on several endpoints, use -p", 2)

        profile = found.profile
        target_system = profile.machine.system
        if profile.pk == context.profile.pk:
            return CommandResult(f"{self.name}: already on this account", 1)
        endpoint_text = f"{profile.freq:.3f} MHz"

        if not bridge.source_allowed(profile, context.machine):
            return _denied(profile, target_system, host, endpoint_text)

        if opts["token"]:
            token = bridge.valid_token(profile, opts["token"])
            if token is None:
                return CommandResult(
                    f"{self.name}: token rejected", 1, scene=scenes.denied_scene(target_system, host, login, endpoint_text)
                )
            bridge.spend_token(token)
            return self.finish(context, profile, args)

        keys_ok = bridge.keys_ok(profile, slugs)

        if bridge.password_required(profile):
            request.session[PENDING_KEY] = {"profile": profile.pk, "key_ok": keys_ok, "mode": self.mode, "args": args}
            return CommandResult(prompt={"kind": "password", "text": f"{login}@{host}'s password: "})

        if keys_ok:
            return self.finish(context, profile, args)

        return _denied(profile, target_system, host, endpoint_text)

    def _parse(self, args):
        """Разбор аргументов: словарь или текст ошибки."""
        opts = {"operands": [], "endpoint": None, "keys": [], "token": None}
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("-p", "-i", "--token", "-t"):
                if i + 1 >= len(args):
                    return f"{self.name}: option {arg} requires an argument"
                value = args[i + 1]
                if arg == "-p":
                    opts["endpoint"] = value
                elif arg == "-i":
                    opts["keys"].append(value)
                else:
                    opts["token"] = value
                i += 2
            elif arg.startswith("-"):
                return f"{self.name}: unsupported option: {arg}\n{self.usage}"
            else:
                opts["operands"].append(arg)
                i += 1
        if len(opts["operands"]) != self.operands:
            return self.usage
        return opts

    def _read_key(self, context, name):
        """Ключ по названию (keyname) из папки секретов этой сессии (/home/.secrets/имя): набор из одного slug или текст ошибки."""
        if name not in keystore.slugs_of(context.session):
            return f"{self.name}: key '{name}' not found in {keystore.SECRETS}"
        return {name}


class BridgeCommand(EntryCommand):
    """rcon: вход на другую машину с переключением рабочего стола."""

    name = "rcon"
    mode = "rcon"
    operands = 1
    usage = "usage: rcon [-p freq] [-i keyname] [--token token] login@host"

    def run(self, context, opts):
        if bridge.total_depth(context.request) >= bridge.MAX_DEPTH:
            return CommandResult(f"{self.name}: too many nested sessions", 1)
        if bridge.shell_depth(context.request):
            return CommandResult(f"{self.name}: not available inside an rshell session, exit it first", 1)
        return self.enter(context, opts, opts["operands"][0])

    def finish(self, context, profile, args):
        bridge.enter(context.request, profile)
        context.cwd = DEFAULT_CWD
        return CommandResult(
            scene=scenes.connect_scene(profile.machine.system, profile.machine.hostname, profile), effects=SWITCH
        )


class RshellCommand(EntryCommand):
    """rshell: вход на другую машину внутри терминала, рабочий стол остаётся на месте. exit возвращает на уровень выше."""

    name = "rshell"
    mode = "rshell"
    operands = 1
    usage = "usage: rshell [-p freq] [-i keyname] [--token token] login@host"

    def run(self, context, opts):
        if bridge.total_depth(context.request) >= bridge.MAX_DEPTH:
            return CommandResult(f"{self.name}: too many nested sessions", 1)
        return self.enter(context, opts, opts["operands"][0])

    def finish(self, context, profile, args):
        bridge.shell_enter(context.request, profile, context.cwd)
        context.cwd = DEFAULT_CWD
        return CommandResult(scene=scenes.connect_scene(profile.machine.system, profile.machine.hostname, profile, cut=False))


class XferCommand(EntryCommand):
    """xfer: перенос файла между машинами.

    Внутри rshell:        xfer :путь_там путь_здесь   (скачать)    xfer путь_здесь :путь_там   (отправить)
    С явным адресом:      xfer [-p частота] [-i ключ] [--token токен] login@host:путь путь_здесь   и обратно
    Путь с двоеточием в начале это путь на машине оболочки; без него путь у себя (откуда вы вошли в rshell)."""

    name = "xfer"
    mode = "xfer"
    operands = 2
    usage = (
        "usage: xfer [-p freq] [-i keyname] [--token token] source destination\n"
        "       one side is :path (inside rshell) or login@host:path"
    )

    def run(self, context, opts):
        first, second = opts["operands"]
        remote = [item for item in (first, second) if self._remote_form(item)]
        if len(remote) != 1:
            return CommandResult(self.usage, 2)

        download = self._remote_form(first) is not None
        address, path = self._remote_form(remote[0])
        local = second if download else first
        args = {"download": download, "remote": path, "local": local}

        if address is None:
            return self.inside_shell(context, args)

        return self.enter(context, opts, address, args)

    @staticmethod
    def _remote_form(text):
        """(login@host или None, путь) для удалённой стороны, иначе None."""
        if text.startswith(":"):
            return None, text[1:]
        head, colon, path = text.partition(":")
        if colon and "@" in head and path:
            return head, path
        return None

    def inside_shell(self, context, args):
        request = context.request
        parent = bridge.shell_parent(request)
        if parent is None:
            return CommandResult(f"{self.name}: not inside an rshell session, use login@host:path", 1)

        local = TerminalContext(session=parent[0], cwd=parent[1], request=request)
        return self.transfer(context, local, args, connect=None)

    def finish(self, context, profile, args):
        remote = TerminalContext(session=bridge.session_for(context.request.user, profile), cwd=DEFAULT_CWD, request=context.request)
        connect = scenes.connect_scene(profile.machine.system, profile.machine.hostname, profile, cut=False, opened=False)
        return self.transfer(remote, context, args, connect=connect)

    def transfer(self, remote, local, args, connect):
        """remote и local это контексты сторон: remote.cwd и local.cwd основа для их относительных путей."""
        remote_path = remote.resolve_path(args["remote"])
        local_path = local.resolve_path(args["local"])
        source, source_path, dest, dest_path = (
            (remote, remote_path, local, local_path) if args["download"] else (local, local_path, remote, remote_path)
        )

        target, error = copy_file(source, source_path, dest, dest_path)
        if error:
            return CommandResult(f"{self.name}: {error}", 1, scene=scenes.transfer_scene(source_path, 0, ok=False, connect=connect))

        return CommandResult(
            f"{self.name}: {source_path} -> {target}: transferred",
            0,
            scene=scenes.transfer_scene(source_path, target, connect=connect),
        )

ENTRY_COMMANDS = {"rcon": BridgeCommand, "rshell": RshellCommand, "xfer": XferCommand}


class ExitCommand(BaseCommand):
    name = "exit"

    def execute(self, context, args):
        request = context.request
        if request is None or bridge.total_depth(request) == 0:
            return CommandResult(f"{self.name}: not inside a remote session", 1)

        if bridge.shell_depth(request):
            left, back = bridge.shell_leave(request)
            context.cwd = back
            host = left.profile.machine.hostname
            return CommandResult(scene=scenes.disconnect_scene(left.profile.machine.system, host, cut=False))

        left = bridge.leave(request)
        context.cwd = DEFAULT_CWD
        host = left.profile.machine.hostname
        return CommandResult(scene=scenes.disconnect_scene(left.profile.machine.system, host), effects=SWITCH)


class BridgeCloseCommand(BaseCommand):
    name = "rcon-close"

    def execute(self, context, args):
        request = context.request
        if request is None or bridge.total_depth(request) == 0:
            return CommandResult(f"{self.name}: no open bridge", 1)

        shell = bridge.shell_leave(request, all_levels=True)
        if bridge.depth(request) == 0:
            # были только оболочки терминала: рабочий стол не менялся
            left, context.cwd = shell
            return CommandResult(scene=scenes.disconnect_scene(left.profile.machine.system, left.profile.machine.hostname, cut=False))

        left = bridge.leave(request, all_levels=True)
        context.cwd = DEFAULT_CWD
        host = left.profile.machine.hostname
        return CommandResult(scene=scenes.disconnect_scene(left.profile.machine.system, host), effects=SWITCH)
