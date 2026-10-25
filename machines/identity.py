"""Как машина представляется в консоли: имя, hid, серийный номер, адрес.

Экран входа и загрузка показывают одно и то же железо, поэтому все данные
берутся отсюда, из машины в базе. hid это MAC основного сетевого адаптера, а
серийный номер и адрес выводятся из него: у одного hid всегда одни и те же.

Вывод идёт в консоль, то есть в исходник страницы: сюда нельзя класть секреты.
"""
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


def serial_for(hid):
    digest = hashlib.sha256(hid.encode()).hexdigest().upper()
    return f"AE-{digest[:4]}-{digest[4:8]}-{digest[8]}"


def address_for(hid):
    octets = hid.split(":")
    try:
        return f"10.40.{int(octets[-2], 16) % 200}.{int(octets[-1], 16) % 250 + 2}"
    except (ValueError, IndexError):
        return "10.40.0.2"


def identity_of(hostname=ENTRY_HOST):
    """Данные машины с таким hostname; если её нет в базе, то запасные значения."""
    hid = Machine.objects.filter(hostname=hostname).values_list("hid", flat=True).first() or UNKNOWN_HID
    return Identity(hostname, hid, serial_for(hid), address_for(hid))
