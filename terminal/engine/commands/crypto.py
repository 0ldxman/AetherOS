from terminal.engine.commands.layered import LayerCommand


class WardCommand(LayerCommand):
    """ward <файл> <пароль>: снять шифрование (слой encrypted)."""

    name = "ward"
    layer = "encrypted"
    done = "decrypted"
    absent = "not encrypted"


class EncCommand(LayerCommand):
    """enc <файл>: раскодировать содержимое (слой base64)."""

    name = "enc"
    layer = "base64"
    done = "decoded"
    absent = "not base64"

class PakCommand(LayerCommand):
    """pak <файл>: распаковать архив (слой archive)."""

    name = "pak"
    layer = "archive"
    done = "unpacked"
    absent = "not an archive"
