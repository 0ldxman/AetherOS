import posixpath

from filesystem.models import SessionFile
from filesystem.states.attempt import peek_top, top_answer
from filesystem.unlock import unlock_file
from terminal.engine.commands.basic import BaseCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult
from terminal.scenes import unlock_scene

_TRUE = {"true", "yes", "1", "да", "вкл"}
_FALSE = {"false", "no", "0", "нет", "выкл"}


def _convert(param, text: str):
    """Значение из командной строки в тип аргумента слоя. ValueError, если
    не получилось."""
    if param.type is bool:
        low = text.lower()

        if low in _TRUE:
            return True

        if low in _FALSE:
            return False

        raise ValueError(text)

    return param.type(text)


class LayerCommand(BaseCommand):
    """Команда, которая снимает верхний слой файла: `команда <файл> [значения]`.

    Подкласс задаёт только слой и тексты:

        class WardCommand(LayerCommand):
            name = "ward"
            layer = "encrypted"
            done = "decrypted"
            absent = "not encrypted"

    Значения после имени файла команда берёт у слоя: это его снимающие
    аргументы (Param(unlock=True)) в том порядке, в котором они описаны в
    классе слоя. У encrypted это пароль, у shifted два числа: skip и count,
    у base64 нет ничего.

    Команда, которой нужно выбирать слой самой (например, утилита с выбором
    шифра), переопределяет execute: разбирает свои аргументы и зовёт
    unlock(context, файл, значения, имя_слоя).
    """

    layer = ""  # имя слоя, который снимает команда
    done = "done"  # что сказать, когда слой снят
    absent = "nothing to do"  # что сказать, если сверху другой слой

    def execute(self, context, args):
        if not args:
            return CommandResult(f"{self.name}: missing file operand", 2)

        return self.unlock(context, args[0], args[1:], self.layer)

    def scene_for(self, context, layer, entry, ok, rest, values):
        """Сцена работы команды. rest это слой, оказавшийся сверху после снятия (или None), values названные игроком."""
        return unlock_scene(layer, entry.path, ok)

    def fail_for(self, context, entry, target, wrong, values):
        """Что сказать, когда слой не снялся: wrong это названные неверно значения."""
        return f"{self.name}: {target}: wrong {wrong}"

    def done_for(self, rest):
        """Что сказать, когда слой снят."""
        return self.done

    def unlock(self, context, target, values, layer, absent=None, finish=None):
        """absent заменяет текст «нечего снимать»; finish(entry, before) зовётся, когда слой снят (before: прогресс файла до
        снятия), и может вернуть строку для ответа."""
        path = context.resolve_path(target)
        fs = VirtualFilesystem(context)

        if not fs.exists(path):
            return CommandResult(
                f"{self.name}: cannot open '{target}': "
                "No such file or directory",
                2,
            )

        if fs.is_directory(path):
            return CommandResult(f"{self.name}: {target}: Is a directory", 1)

        entry = fs.get_file(path)
        raw_state = entry.session_file.state if entry.session_file else ""
        name = posixpath.basename(entry.path)
        top = peek_top(entry.machine_file.state, raw_state)

        if top is None or top.state.name != layer:
            # Сверху чужой слой: отвечает он (`команда: ...` в описании
            # файла) или говорим, что делать нечего. Попытка не тратится.
            text = top_answer(
                entry.machine_file.state,
                raw_state,
                self.name,
                path=entry.path,
                name=name,
                only_top=True,
            )

            return CommandResult(
                f"{self.name}: {target}: "
                f"{text if text is not None else (absent or self.absent)}",
                1,
            )

        params = [p for p in top.state.params if p.unlock]

        if len(values) > len(params):
            return CommandResult(f"{self.name}: too many arguments", 2)

        if len(values) < len(params):
            return CommandResult(
                f"{self.name}: missing {params[len(values)].name}", 2
            )

        given = {}

        for param, text in zip(params, values):
            try:
                given[param.name] = _convert(param, text)
            except ValueError:
                return CommandResult(
                    f"{self.name}: invalid {param.name}: {text}", 2
                )

        session_file = entry.session_file

        if session_file is None:
            session_file, _ = SessionFile.objects.get_or_create(
                session=context.session,
                path=entry.path,
                defaults={"file": entry.machine_file},
            )

        before = session_file.state
        outcome = unlock_file(session_file, given)

        rest = peek_top(entry.machine_file.state, outcome.session_file.state)

        if outcome.result.removed:
            lines = [f"{self.name}: {target}: {self.done_for(rest)}"]
            extra = finish(entry, before) if finish else None
            lines += [extra] if extra else []
            code = 0
        else:
            wrong = ", ".join(outcome.result.wrong)
            lines = [self.fail_for(context, entry, target, wrong, values)]
            code = 1

        arrived = sum(1 for item in outcome.mail if item.delivered and item.immediate)
        notice = [f"intercom: {arrived} new message{'s' if arrived != 1 else ''}"] if arrived else []
        return CommandResult(
            "\n".join(lines + outcome.say + notice),
            code,
            scene=self.scene_for(context, layer, entry, bool(outcome.result.removed), rest, values),
            effects=outcome.effects or None,
        )