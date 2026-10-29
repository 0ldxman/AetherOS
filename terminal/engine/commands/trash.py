"""Корзина: del (убрать файл в корзину записи), rcvr (вернуть, но повреждённым), wipe (очистить корзину).

del и wipe спрашивают подтверждение (del -f и wipe -f без вопроса). Вопрос это prompt вида confirm, ответ приходит
отдельным запросом (terminal.views.execute), а что собирались сделать, лежит в Django-сессии.
"""
from filesystem.layers.unlock import fire_file_event
from filesystem.trash import empty_trash, in_trash, trashed
from terminal.engine import trash
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.report import hook_report
from terminal.engine.context import TerminalContext
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult
from terminal import scenes

CONFIRM_KEY = "confirm_pending"
YES = {"y", "yes", "д", "да"}


def _flags(args):
    """(флаги, операнды): -f, -r (и вместе -rf), -- заканчивает флаги."""
    flags, operands, done = set(), [], False
    for arg in args:
        if done or not arg.startswith("-") or arg == "-":
            operands.append(arg)
        elif arg == "--":
            done = True
        else:
            flags |= set(arg[1:])
    return flags, operands


def answer_confirm(request, text, session, cwd):
    """Ответ на вопрос del или wipe. Возвращает (результат, папка)."""
    pending = request.session.pop(CONFIRM_KEY, None)
    if not pending or text.strip().lower() not in YES:
        return CommandResult(), cwd

    context = TerminalContext(session=session, cwd=cwd, request=request)
    if pending["mode"] == "wipe":
        return Wipe.finish(context), cwd
    return Del.finish(context, pending["paths"], pending["recursive"]), cwd


class Del(BaseCommand):
    name = "del"
    usage = "usage: del [-f] [-r] file..."

    def execute(self, context, args):
        flags, operands = _flags(args)
        unknown = flags - {"f", "r"}
        if unknown:
            return CommandResult(f"{self.name}: unsupported option: -{sorted(unknown)[0]}\n{self.usage}", 2)
        if not operands:
            return CommandResult(self.usage, 2)

        recursive = "r" in flags
        problems, paths = [], []
        for operand in operands:
            error = self.check(context, operand, recursive)
            if error:
                problems.append(f"{self.name}: cannot remove '{operand}': {error}")
            else:
                paths.append(context.resolve_path(operand))

        text = "\n".join(problems)
        if not paths:
            return CommandResult(text, 1)

        if "f" in flags:
            result = self.finish(context, paths, recursive)
            return CommandResult(
                "\n".join(filter(None, [text, result.output])), 1 if problems else 0, scene=result.scene, effects=result.effects
            )

        names = ", ".join(f"'{p}'" for p in paths)
        context.request.session[CONFIRM_KEY] = {"mode": "del", "paths": paths, "recursive": recursive}
        return CommandResult(text, 1 if problems else 0, prompt={"kind": "confirm", "text": f"{self.name}: move {names} to the trash? (y/n) "})

    @staticmethod
    def check(context, operand, recursive):
        path = context.resolve_path(operand)
        fs = VirtualFilesystem(context)
        if not fs.exists(path):
            return "No such file or directory"
        if in_trash(path, context.trash_dir):
            return "already in the trash (use wipe)"
        found = trash.under(fs._entries(), path)
        if fs.is_directory(path) and not recursive:
            return "Is a directory"
        return trash.protection(context, path, found)

    @classmethod
    def finish(cls, context, paths, recursive):
        moved = []
        for path in paths:
            if cls.check(context, path, recursive) is None:     # за время вопроса что-то могло измениться
                moved += trash.trash(context, path)
        if not moved:
            return CommandResult()

        # хуки on delete: файл уже в корзине, а в текстах хука {path} прежний путь
        lines, effects = hook_report([fire_file_event(context.view, new_path, "delete", original) for new_path, original in moved])
        context.invalidate()
        count = len(moved)
        text = "\n".join([f"del: {count} file{'s' if count != 1 else ''} moved to the trash", *lines])
        return CommandResult(text, 0, scene=scenes.trash_scene(count), effects=effects)


class Rcvr(BaseCommand):
    name = "rcvr"
    usage = "usage: rcvr file-in-trash [destination]"

    def execute(self, context, args):
        if not args or len(args) > 2:
            return CommandResult(self.usage, 2)

        path = context.resolve_path(args[0])
        if not in_trash(path, context.trash_dir) or path == context.trash_dir:
            return CommandResult(f"{self.name}: {args[0]}: not in the trash", 1)

        dest = context.resolve_path(args[1]) if len(args) > 1 else None
        restored, error = trash.recover(context, path, dest)
        if error:
            return CommandResult(f"{self.name}: {args[0]}: {error}", 1)

        lines, effects = hook_report(fired for _, fired in restored)
        text = "\n".join([f"{self.name}: {', '.join(target for target, _ in restored)}: recovered, the data is damaged", *lines])
        return CommandResult(text, 0, scene=scenes.recover_scene(path), effects=effects)


class Wipe(BaseCommand):
    name = "wipe"
    usage = "usage: wipe [-f]"

    def execute(self, context, args):
        flags, operands = _flags(args)
        if operands or flags - {"f"}:
            return CommandResult(self.usage, 2)

        count = len(trashed(context.view, context.trash_dir))
        if not count:
            return CommandResult(f"{self.name}: the trash is empty")
        if "f" in flags:
            return self.finish(context)

        context.request.session[CONFIRM_KEY] = {"mode": "wipe"}
        return CommandResult(prompt={"kind": "confirm", "text": f"{self.name}: remove {count} file{'s' if count != 1 else ''} for good? (y/n) "})

    @staticmethod
    def finish(context):
        count = empty_trash(context.view, context.trash_dir)
        context.invalidate()
        return CommandResult(f"wipe: {count} file{'s' if count != 1 else ''} removed", 0, scene=scenes.wipe_scene(count))
