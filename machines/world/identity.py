"""Как машина представляется в консоли: имя, hid, серийный номер, адрес, ключ узла.

Экран входа и загрузка показывают одно и то же железо, поэтому все данные
берутся отсюда, из машины в базе. hid это MAC основного сетевого адаптера (у клонов он общий). Серийный номер, адрес и
ключ узла автор может задать у машины сам или сгенерировать; пока поле пусто, значение выводится из hid: у одного hid всегда
одно и то же. Адрес у радио-ОС это частота («18.979», МГц), у остальных сетевой адрес («10.40.7.12»).

Вывод идёт в консоль, то есть в исходник страницы: сюда нельзя класть секреты.
"""
import base64
import hashlib
import re
import secrets
from dataclasses import dataclass

from machines.models import Machine
from machines.world.blackout import RADIO

UNKNOWN_HID = "00:00:00:00:00:00"
ENTRY_HOST = "aether-main"
CORE_HOST = "aether-core"   # центральный узел: на него смотрят журналы аудита и uplink


@dataclass(frozen=True)
class Identity:
    hostname: str
    hid: str            # MAC основного адаптера
    serial: str
    address: str        # частота (радио-ОС, МГц) или сетевой адрес
    host_key: str       # отпечаток ключа узла: SHA256:...
    randomart: tuple    # картинка отпечатка (строки), как у ssh


def serial_for(hid):
    digest = hashlib.sha256(hid.encode()).hexdigest().upper()
    return f"AE-{digest[:4]}-{digest[4:8]}-{digest[8]}"


def address_for(hid):
    octets = hid.split(":")
    try:
        return f"10.40.{int(octets[-2], 16) % 200}.{int(octets[-1], 16) % 250 + 2}"
    except (ValueError, IndexError):
        return "10.40.0.2"


def freq_for(hid):
    """Частота узла в МГц (3.000-29.999), из hid; пока вместо поля в базе."""
    value = int.from_bytes(hashlib.sha256((hid + "/freq").encode()).digest()[:4], "big")
    return f"{3 + (value % 27000) / 1000:.3f}"


def host_key_digest(hid):
    return hashlib.sha256((hid + "/host-key").encode()).digest()


def fingerprint_of(digest):
    """Отпечаток ключа узла в привычном виде: SHA256:<base64 без =>."""
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def fingerprint_for(hid):
    return fingerprint_of(host_key_digest(hid))


FINGERPRINT = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


def digest_of(fingerprint):
    """Байты, которым соответствует отпечаток (по ним рисуется картинка). Не отпечаток: хэш текста."""
    if FINGERPRINT.match(fingerprint or ""):
        return base64.b64decode(fingerprint[len("SHA256:"):] + "=")
    return hashlib.sha256((fingerprint or "").encode()).digest()


def generate_serial():
    digits = secrets.token_hex(5).upper()
    return f"AE-{digits[:4]}-{digits[4:8]}-{digits[8]}"


def generate_address(system):
    if system == RADIO:
        return f"{3 + secrets.randbelow(27000) / 1000:.3f}"
    return f"10.40.{secrets.randbelow(200)}.{secrets.randbelow(250) + 2}"


def generate_host_key():
    return fingerprint_of(secrets.token_bytes(32))


def client_fingerprint(who):
    """Отпечаток ключа клиента этого посетителя: у одного человека всегда один."""
    return fingerprint_for("client:" + str(who))


def randomart_of(fingerprint, title="ED25519 256", footer="SHA256"):
    """Картинка отпечатка («блуждающий слон», как у ssh): у одного ключа всегда одна."""
    width, height = 17, 9
    field = [[0] * width for _ in range(height)]
    x, y = width // 2, height // 2
    start = (x, y)

    for byte in digest_of(fingerprint):
        for shift in (0, 2, 4, 6):
            bits = (byte >> shift) & 3
            x = min(max(x + (1 if bits & 1 else -1), 0), width - 1)
            y = min(max(y + (1 if bits & 2 else -1), 0), height - 1)
            field[y][x] += 1

    symbols = " .o+=*BOX@%&#/^"
    rows = []
    for j in range(height):
        row = ""
        for i in range(width):
            if (i, j) == start:
                row += "S"
            elif (i, j) == (x, y):
                row += "E"
            else:
                row += symbols[min(field[j][i], len(symbols) - 1)]
        rows.append(f"|{row}|")

    top = "+" + f"[{title}]".center(width, "-") + "+"
    bottom = "+" + f"[{footer}]".center(width, "-") + "+"
    return (top, *rows, bottom)


def randomart_for(hid, **kwargs):
    return randomart_of(fingerprint_for(hid), **kwargs)


def address_of(hid, system):
    """Адрес, выведенный из hid: частота у радио-ОС, сетевой адрес у остальных."""
    return freq_for(hid) if system == RADIO else address_for(hid)


def identity_of(hostname=ENTRY_HOST):
    """Данные машины с таким hostname; если её нет в базе, то запасные значения. Пустое поле машины заменяется значением из hid."""
    machine = Machine.objects.filter(hostname=hostname).first()
    if machine is None:
        return Identity(hostname, UNKNOWN_HID, serial_for(UNKNOWN_HID), address_of(UNKNOWN_HID, RADIO), fingerprint_for(UNKNOWN_HID),
                        randomart_for(UNKNOWN_HID))
    return of_machine(machine)


def of_machine(machine):
    hid = machine.hid
    host_key = machine.host_key or fingerprint_for(hid)
    return Identity(
        machine.hostname or "", hid, machine.serial or serial_for(hid), machine.address or address_of(hid, machine.system), host_key,
        randomart_of(host_key),
    )
