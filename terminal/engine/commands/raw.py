from filesystem.size import file_size
from terminal.engine.commands.layered import LayerCommand
from terminal.scenes import repair_scene


class RprCommand(LayerCommand):
    """rpr <файл>: восстановить файл, снимает один слой damaged. Если под ним ещё один, сцена и ответ говорят, что нужна
    ещё одна починка."""

    name = "rpr"
    layer = "damaged"
    done = "repaired"
    absent = "nothing to repair"

    @staticmethod
    def _more(rest):
        return rest is not None and rest.state.name == "damaged"

    def scene_for(self, layer, entry, ok, rest):
        return repair_scene(entry.path, file_size(entry.machine_file), ok, self._more(rest))

    def done_for(self, rest):
        return "repaired with errors, further repair required" if self._more(rest) else self.done


class BlkCommand(LayerCommand):
    """blk <файл> <skip> <count>: прочитать нужные блоки (слой shifted)."""

    name = "blk"
    layer = "shifted"
    done = "blocks read"
    absent = "nothing to read"


class CvtCommand(LayerCommand):
    """cvt <файл> <формат>: преобразовать файл в другой формат (слой disguised)."""

    name = "cvt"
    layer = "disguised"
    done = "converted"
    absent = "nothing to convert"
