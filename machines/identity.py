"""Как машина представляется в консоли: имя, hid, серийный номер, адрес.

Экран входа и загрузка показывают одно и то же железо, поэтому все данные
берутся отсюда, из машины в базе. hid это MAC основного сетевого адаптера, а
серийный номер и адрес выводятся из него: у одного hid всегда одни и те же.

Вывод идёт в консоль, то есть в исходник страницы: сюда нельзя класть секреты.
"""
import base64
import hashlib
from dataclasses import dataclass

from .models import Machine

UNKNOWN_HID = "00:00:00:00:00:00"
ENTRY_HOST = "aether-main"
CORE_HOST = "aether-core"   # центральный узел: на него смотрят журналы аудита и uplink


@dataclass(frozen=True)
class Identity:
    hostname: str
    hid: str            # MAC основного адаптера
    serial: str
    address: str
    host_key: str       # отпечаток ключа узла: SHA256:...
    randomart: tuple    # картинка отпечатка (строки), как у ssh
    freq: str           # частота узла, МГц, например «14.230»
    callsign: str       # позывной узла в эфире


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


def callsign_for(hid):
    return "AEM-" + hashlib.sha256((hid + "/call").encode()).hexdigest()[:3].upper()


def host_key_digest(hid):
    return hashlib.sha256((hid + "/host-key").encode()).digest()


def fingerprint_for(hid):
    """Отпечаток ключа узла в привычном виде: SHA256:<base64 без =>."""
    return "SHA256:" + base64.b64encode(host_key_digest(hid)).decode().rstrip("=")


def client_fingerprint(who):
    """Отпечаток ключа клиента этого посетителя: у одного человека всегда один."""
    return fingerprint_for("client:" + str(who))


def randomart_for(hid, title="ED25519 256", footer="SHA256"):
    """Картинка отпечатка («блуждающий слон», как у ssh): у одного ключа всегда одна."""
    width, height = 17, 9
    field = [[0] * width for _ in range(height)]
    x, y = width // 2, height // 2
    start = (x, y)

    for byte in host_key_digest(hid):
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


def identity_of(hostname=ENTRY_HOST):
    """Данные машины с таким hostname; если её нет в базе, то запасные значения."""
    hid = Machine.objects.filter(hostname=hostname).values_list("hid", flat=True).first() or UNKNOWN_HID
    return Identity(
        hostname, hid, serial_for(hid), address_for(hid), fingerprint_for(hid), randomart_for(hid),
        freq_for(hid), callsign_for(hid),
    )
