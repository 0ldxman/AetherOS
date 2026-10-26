"""Сеть: nreq (запрос к ресурсу) и nget (скачать файл ресурса в сессию машины).

Ресурсы описывает автор (machines.NetResource): адрес, ответ, файлы, условие по ключам и токен. Ресурс, которого игрок
по ключам не видит, отвечает как несуществующий. Реальной сети нет.
"""
from machines.models import NetResource
from secure.access import satisfied
from terminal import net_scenes as scenes
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.result import CommandResult
from terminal.engine.transfer import place_file
from wiki.access import player_keys


class NetCommand(BaseCommand):
    options = ("--token", "-t")

    def execute(self, context, args):
        opts = self._parse(args)
        if isinstance(opts, str):
            return CommandResult(opts, 2)

        address, _, name = opts["operands"][0].partition("/")
        system = context.machine.system
        resource = self.find(context, address)
        if resource is None:
            return CommandResult(
                f"{self.name}: could not resolve host '{address}'", 1, scene=scenes.unreachable_scene(system, address)
            )

        if resource.token and opts["token"] != resource.token:
            return CommandResult(f"{self.name}: 401 unauthorized", 1, scene=scenes.refused_scene(system, address))

        return self.handle(context, resource, name, opts)

    def find(self, context, address):
        resource = NetResource.objects.filter(address=address.strip().lower()).first()
        if resource is None:
            return None

        request = context.request
        keys = player_keys(request.user) if request is not None else frozenset()
        if resource.key_condition is not None and not satisfied(resource.key_condition, keys):
            return None
        return resource

    def _parse(self, args):
        opts = {"operands": [], "token": None, "output": None}
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in self.options:
                if i + 1 >= len(args):
                    return f"{self.name}: option {arg} requires an argument"
                if arg in ("--token", "-t"):
                    opts["token"] = args[i + 1]
                else:
                    opts["output"] = args[i + 1]
                i += 2
            elif arg.startswith("-"):
                return f"{self.name}: unsupported option: {arg}\n{self.usage}"
            else:
                opts["operands"].append(arg)
                i += 1
        return opts if len(opts["operands"]) == 1 else self.usage


class NreqCommand(NetCommand):
    name = "nreq"
    usage = "usage: nreq [--token token] address"

    def handle(self, context, resource, name, opts):
        text = resource.response.rstrip()
        files = list(resource.files.values_list("name", flat=True)) if resource.listing else []
        if files:
            text += ("\n\n" if text else "") + "files:\n" + "\n".join(f"  {item}" for item in files)
        return CommandResult(text, 0, scene=scenes.request_scene(context.machine.system, resource.address))


class NgetCommand(NetCommand):
    name = "nget"
    usage = "usage: nget [--token token] [-o path] address/file"
    options = ("--token", "-t", "-o")

    def handle(self, context, resource, name, opts):
        system = context.machine.system
        if not name:
            return CommandResult(self.usage, 2)

        item = resource.files.filter(name=name).select_related("file").first()
        if item is None:
            return CommandResult(
                f"{self.name}: 404 not found: {resource.address}/{name}", 1, scene=scenes.refused_scene(system, resource.address)
            )

        dest = context.resolve_path(opts["output"] or name)
        target, error = place_file(context, item.file, "", dest, name)
        if error:
            return CommandResult(f"{self.name}: {error}", 1)

        return CommandResult(
            f"{self.name}: {resource.address}/{name} -> {target}: saved",
            0,
            scene=scenes.download_scene(system, resource.address, name),
        )
