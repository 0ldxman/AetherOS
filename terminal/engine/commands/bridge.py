"""Команды моста: bridge (войти на другую машину), exit (на уровень выше), bridge-close (закрыть всё).

Условия входа и стек сессий в machines/bridge.py. Здесь разбор команды, чтение файла-ключа (-i), запрос пароля
и ответы в духе ssh. Отказ не говорит, какое условие не выполнено: только перечень способов записи,
Permission denied (publickey,password). Нет машины или записи называется прямо.
"""
from filesystem.states.attempt import peek_top
from machines import bridge
from terminal import bridge_scenes as scenes
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.context import DEFAULT_CWD
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult

PENDING_KEY = "bridge_pending"
SWITCH = [{"op": "switch"}]


def _denied(profile, system, host, endpoint=None):
    listed = ",".join(bridge.methods(profile)) or "none"
    return CommandResult(
        f"Permission denied ({listed}).", 1, scene=scenes.denied_scene(system, host, profile.login, endpoint)
    )


def open_bridge(request, profile):
    """Условия выполнены: входим, терминал начинает новую оболочку, рабочий стол сменится."""
    session = bridge.enter(request, profile)
    system = profile.machine.system
    return CommandResult(scene=scenes.connect_scene(system, profile.machine.hostname, profile), effects=SWITCH), session


def answer_prompt(request, text):
    """Ответ на запрос пароля. Возвращает (результат, новая папка или None)."""
    from machines.models import MachineProfile

    pending = request.session.pop(PENDING_KEY, None)
    profile = MachineProfile.objects.filter(pk=(pending or {}).get("profile")).select_related("machine").first()
    if profile is None:
        return CommandResult(), None

    if pending["key_ok"] and bridge.password_ok(profile, text):
        result, _ = open_bridge(request, profile)
        return result, DEFAULT_CWD

    return _denied(profile, profile.machine.system, profile.machine.hostname, f"{profile.freq:.3f} MHz"), None


class BridgeCommand(BaseCommand):
    name = "bridge"
    usage = "usage: bridge [-p freq] [-i keyfile] [--token token] login@host"

    def execute(self, context, args):
        request = context.request
        if request is None or not request.user.is_authenticated:
            return CommandResult(f"{self.name}: not available here", 1)

        opts = self._parse(args)
        if isinstance(opts, str):
            return CommandResult(opts, 2)

        request.session.pop(PENDING_KEY, None)
        login, _, host = opts["target"].partition("@")
        if not login or not host:
            return CommandResult(self.usage, 2)

        endpoint = None
        if opts["endpoint"] is not None:
            endpoint = bridge.parse_endpoint(opts["endpoint"])
            if endpoint is None:
                return CommandResult(f"{self.name}: bad endpoint '{opts['endpoint']}'", 2)

        if bridge.depth(request) >= bridge.MAX_DEPTH:
            return CommandResult(f"{self.name}: too many nested bridges", 1)

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
            result, _ = open_bridge(request, profile)
            context.cwd = DEFAULT_CWD
            return result

        keys_ok = bridge.keys_ok(profile, slugs)

        if bridge.password_required(profile):
            request.session[PENDING_KEY] = {"profile": profile.pk, "key_ok": keys_ok}
            return CommandResult(prompt={"kind": "password", "text": f"{login}@{host}'s password: "})

        if keys_ok:
            result, _ = open_bridge(request, profile)
            context.cwd = DEFAULT_CWD
            return result

        return _denied(profile, target_system, host, endpoint_text)

    def _parse(self, args):
        """Разбор аргументов: словарь или текст ошибки."""
        opts = {"target": None, "endpoint": None, "keys": [], "token": None}
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
            elif opts["target"] is None:
                opts["target"] = arg
                i += 1
            else:
                return self.usage
        return opts if opts["target"] else self.usage

    def _read_key(self, context, path):
        """Ключи из файла-ключа: набор slug или текст ошибки. Файл со слоями «не читается»."""
        target = context.resolve_path(path)
        entry = VirtualFilesystem(context).get_file(target)
        if entry is None:
            return f"{self.name}: identity file {path} not found"
        raw_state = entry.session_file.state if entry.session_file else ""
        if peek_top(entry.machine_file.state, raw_state) is not None:
            return f'Load key "{path}": invalid format'
        return set(entry.machine_file.keys.values_list("key__slug", flat=True))


class ExitCommand(BaseCommand):
    name = "exit"

    def execute(self, context, args):
        request = context.request
        if request is None or bridge.depth(request) == 0:
            return CommandResult(f"{self.name}: not inside a bridge session", 1)

        left = bridge.leave(request)
        context.cwd = DEFAULT_CWD
        host = left.profile.machine.hostname
        return CommandResult(scene=scenes.disconnect_scene(left.profile.machine.system, host), effects=SWITCH)


class BridgeCloseCommand(BaseCommand):
    name = "bridge-close"

    def execute(self, context, args):
        request = context.request
        if request is None or bridge.depth(request) == 0:
            return CommandResult(f"{self.name}: no open bridge", 1)

        left = bridge.leave(request, all_levels=True)
        context.cwd = DEFAULT_CWD
        host = left.profile.machine.hostname
        return CommandResult(scene=scenes.disconnect_scene(left.profile.machine.system, host), effects=SWITCH)
