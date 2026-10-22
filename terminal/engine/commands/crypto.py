from terminal.engine.commands.layered import LayerCommand


class CphCommand(LayerCommand):
    """cph <файл> <пароль>: снять шифрование (слой encrypted)."""

    name = "cph"
    layer = "encrypted"
    done = "decrypted"
    absent = "not encrypted"


class B256Command(LayerCommand):
    """b256 <файл>: раскодировать содержимое (слой base64)."""

    name = "b256"
    layer = "base64"
    done = "decoded"
    absent = "not base64"