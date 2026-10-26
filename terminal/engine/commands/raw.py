from terminal.engine.commands.layered import LayerCommand


class RprCommand(LayerCommand):
    name = "rpr"
    layer = "damaged"
    done = "repaired"
    absent = "nothing to repair"

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
