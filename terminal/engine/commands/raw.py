from terminal.engine.commands.layered import LayerCommand


class RprCommand(LayerCommand):
    name = "rpr"
    layer = "damaged"
    done = "repaired"
    absent = "nothing to repair"