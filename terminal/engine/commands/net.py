"""Сеть: nreq (запрос по адресу) и nget (скачать файл в сессию машины).

Сервер и его страницы описывает автор (machines.NetResource и NetNode). Адрес можно писать как URL:
https://apollo.com/info/ и apollo.com/info это одно и то же. Сервер или узел, которого игрок по ключам не видит,
отвечает как несуществующий. Реальной сети нет.
"""
from machines.models import LISTING_TAG, NetNode, NetResource, split_url
from secure.access import satisfied
from terminal.scenes import net as scenes
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.result import CommandResult
from terminal.engine.transfer import place_item
from wiki.access import request_keys


class Site:
    """Сервер глазами игрока: узлы, которые ему видны по ключам."""

    def __init__(self, resource, keys):
        self.resource = resource
        self.nodes = {
            node.path: node
            for node in resource.nodes.select_related("item")
            if node.key_condition is None or satisfied(node.key_condition, keys)
        }

    def children(self, path):
        """Что лежит прямо внутри path: [(имя, папка ли)], папки первыми. Папка это и узел с вложенным, и просто часть пути."""
        prefix = path + "/" if path else ""
        found = {}
        for other in self.nodes:
            if not other.startswith(prefix) or other == path:
                continue
            head, _, rest = other[len(prefix):].partition("/")
            found[head] = found.get(head, False) or bool(rest)
        return sorted(found.items(), key=lambda item: (not item[1], item[0].lower()))

    def listing(self, path):
        return "\n".join(name + ("/" if folder else "") for name, folder in self.children(path))

    def exists(self, path):
        return path in self.nodes or bool(self.children(path)) or (not path)

    def page(self, path):
        """Ответ на nreq для пути: текст узла с подставленным {listing}, а без текста один список."""
        node = self.nodes.get(path)
        text = (node.response if node else "").rstrip()
        listing = self.listing(path)
        if not text.strip():
            return listing
        return text.replace(LISTING_TAG, listing).strip("\n") if LISTING_TAG in text else text


class NetCommand(BaseCommand):
    options = ("--token", "-t")
    privilege = ""              # что нужно записи, чтобы так обратиться к серверу

    def execute(self, context, args):
        if self.privilege:
            context.need(self.privilege)
        opts = self._parse(args)
        if isinstance(opts, str):
            return CommandResult(opts, 2)

        scheme, host, path = split_url(opts["operands"][0])
        address = f"{scheme}://{host}" if scheme else host
        system = context.machine.system
        # сервер со схемой отвечает только на неё, без схемы на любую (и на запрос без схемы)
        found = {item.address: item for item in NetResource.objects.filter(address__in=[address, host])}
        resource = found.get(address) or found.get(host)
        request = context.request
        keys = request_keys(request) if request is not None else frozenset()

        if resource is None or (resource.key_condition is not None and not satisfied(resource.key_condition, keys)):
            return CommandResult(
                f"{self.name}: could not resolve host '{address}'", 1, scene=scenes.unreachable_scene(system, address)
            )

        site = Site(resource, keys)
        node = site.nodes.get(path)
        required = [token for token in (resource.token, node.token if node else "") if token]
        if any(opts["token"] != token for token in required):
            return CommandResult(f"{self.name}: 401 unauthorized", 1, scene=scenes.refused_scene(system, address))

        if not site.exists(path):
            return CommandResult(
                f"{self.name}: 404 not found: {address}/{path}", 1, scene=scenes.refused_scene(system, address)
            )

        return self.handle(context, site, path, opts)

    def _parse(self, args):
        opts = {"operands": [], "token": None, "output": None}
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in self.options:
                if i + 1 >= len(args):
                    return f"{self.name}: option {arg} requires an argument"
                opts["output" if arg == "-o" else "token"] = args[i + 1]
                i += 2
            elif arg.startswith("-"):
                return f"{self.name}: unsupported option: {arg}\n{self.usage}"
            else:
                opts["operands"].append(arg)
                i += 1
        return opts if len(opts["operands"]) == 1 else self.usage


class NreqCommand(NetCommand):
    name = "nreq"
    usage = "usage: nreq [--token token] address[/path]"

    def handle(self, context, site, path, opts):
        return CommandResult(
            site.page(path), 0, scene=scenes.request_scene(context.machine.system, site.resource.address)
        )


class NgetCommand(NetCommand):
    name = "nget"
    usage = "usage: nget [--token token] [-o path] address/path/to/file"
    options = ("--token", "-t", "-o")
    privilege = "transfer"

    def handle(self, context, site, path, opts):
        system = context.machine.system
        address = site.resource.address
        node = site.nodes.get(path)

        if node is None or node.item is None:
            return CommandResult(f"{self.name}: {address}/{path}: not a file", 1, scene=scenes.refused_scene(system, address))

        name = path.rsplit("/", 1)[-1]
        dest = context.resolve_path(opts["output"] or name)
        target, error = place_item(context, node.item, "", dest, name)
        if error:
            return CommandResult(f"{self.name}: {error}", 1)

        return CommandResult(
            f"{self.name}: {address}/{path} -> {target}: saved", 0, scene=scenes.download_scene(system, address, name)
        )
