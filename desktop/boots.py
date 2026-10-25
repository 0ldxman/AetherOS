"""Загрузки машин: консольные сцены, что видит игрок на удалённой консоли.

У каждой операционной системы своя загрузка. Aether это не Linux и не его
стилизация: у системы своё ядро (aek), загрузчик (aeboot), инициализация (aeinit)
и контроллер управления (aemc). Всё пишется «по-настоящему» (подсистемы, время от
старта, проверки подписей, устройства), только на языке Aether. Тон холодный и
деловой: нижний регистр, выровненные колонки.

Данные машины (имя, hid, серийный номер, адрес) берутся из machines/identity.py,
поэтому загрузка и экран входа показывают одно и то же железо.

Viper, Essig и Shroud получат свои функции рядом (у кого-то система может быть
старше, с пиксельным шрифтом и «настоящим» BIOS) и подключатся в BOOTS.

Полная загрузка: подключение, прошивка, загрузчик, ядро, службы. При повторном
заходе в рамках вкладки игроку показывают короткую: только подключение и службы.
"""
import hashlib

from console.scene import Scene
from machines.identity import CORE_HOST

WIDTH = 12          # ширина подписей в таблицах прошивки

# (имя, описание, результат, пояснение, длительность мс)
UNITS = (
    ("keyagent", "secure key agent", "OK", None, (150, 500)),
    ("authd", "clearance daemon", "OK", None, (200, 600)),
    ("archive", "/archive mounted (read-only)", "OK", None, (250, 700)),
    ("uplink", f"link to {CORE_HOST}", "OK", None, (1200, 2300)),
    ("telemetry", "sector 12: no response, skipping", "WARN", None, (700, 1300)),
    ("relay", "message relay", "OK", None, (150, 500)),
    ("archived", "archive service", "OK", None, (200, 600)),
    ("watcher", "legacy watcher exited (code 0x0f)", "FAIL", None, (300, 800)),
    ("desktop", "target reached", "OK", None, (250, 600)),
)

# время от старта ядра (с), подсистема, текст; None вместо текста: строка-задача ниже
def _kernel_lines(ident):
    return (
        (0.000000, "aek", "aether kernel 5.8.14-hal (forge-03) #1 smp 2020-09-02"),
        (0.000000, "aek", "cmdline: vault=/dev/vault0 ro console=com1 quiet=2"),
        (0.001870, "efi", "boot services exited, memory map 38 entries"),
        (0.004211, "cpu", "AETHER QX-9, 8 cores, microcode 0x0a201009"),
        (0.007803, "mem", "64 GiB ecc, 4 channels, 0 errors"),
        (0.011302, "acpi", "tables ok (rsdp 0x00000000000f6a90)"),
        (0.019870, "pci", "0000:00 enumerated, 14 devices, 2 bridges"),
        (0.024115, "nvme", "nvme0: AETHER-VAULT 4 TB, 1 namespace, queue depth 1024"),
        (0.031440, "net", f"eth0: {ident.hid} link up 10 Gbps full duplex"),
        (0.031902, "net", "eth1: no carrier"),
        (0.058230, "tpm", "tpm0: 2.0, pcr banks sha256, measured boot log 18 events"),
        (0.312874, "tamper", "chassis seal intact"),
        (0.318002, "rng", "entropy pool seeded (hwrng)"),
    )


def _pcr_digest(ident):
    return "sha256:" + hashlib.sha256((ident.hid + "pcr").encode()).hexdigest()[:32]


def _check(s, label, result):
    """Проверка прошивки: «label ........ result», результат зелёный."""
    s.task(f"{label:<20}", result, ms=(300, 800), style="success")


def _connect(s, ident):
    s.say("> ", end=False, cursor=True).type(f"aemc attach {ident.hostname}", speed=30)
    s.say("aemc 1.7  ·  management controller", style="dim")
    s.wait((200, 450))
    s.task("opening channel ", "OK", ms=(500, 1100))
    s.say("console attached (escape: ~.)", style="dim")
    s.wait((150, 350))
    s.task("waiting for console ", "OK", ms=(900, 1900))


def _firmware(s, ident):
    s.cut().wait((200, 400))
    s.say("AETHER FIRMWARE 2.4.1", ("  ·  uefi 2.8  ·  build 2020-02-18", "dim"))
    s.blank()
    s.row("node", ident.hostname, width=WIDTH)
    s.row("serial", ident.serial, width=WIDTH)
    s.blank()

    s.say("-- platform --", style="dim")
    s.row("cpu", "AETHER QX-9  8 cores  3.8 GHz", width=WIDTH)
    s.count("memory", 64, unit=" GiB", ms=(600, 1100), width=WIDTH, note="ecc, 4 channels")
    s.row("storage", "nvme0  AETHER-VAULT 4 TB  encrypted", width=WIDTH)
    s.say("network".ljust(WIDTH), f"eth0 10 Gbps up  {ident.hid}")
    s.say(" " * WIDTH, "eth1 ", ("no carrier", "warning"))
    s.row("bmc", "aemc 1.7  online", width=WIDTH)
    s.wait((200, 400)).blank()

    s.say("-- security --", style="dim")
    _check(s, "secure boot", "enabled")
    _check(s, "tpm 2.0", "present")
    _check(s, "measured boot", "sealed")
    s.row("pcr 0-7", _pcr_digest(ident), "dim", width=WIDTH)
    _check(s, "firmware signature", "verified")
    s.wait((500, 900))


def _bootloader(s):
    s.cut()
    s.say("AEBOOT 2.1", ("  ·  signed loader", "dim"))
    s.blank()
    s.row("entry", "aether 9.1 (halcyon)", note="default", width=WIDTH)
    s.say("recovery".ljust(WIDTH), ("aether 9.1 recovery  ", "dim"), ("[clearance L5 required]", "error"))
    s.blank()
    s.bar("loading aek 5.8.14-hal   ", ms=(900, 1600))
    s.task("verifying image signature ", "OK", ms=(400, 800))
    s.task("measuring into pcr 8-9 ", "OK", ms=(200, 500))
    s.wait((300, 600))


def _kernel(s, ident):
    s.cut()
    for at, tag, message in _kernel_lines(ident):
        s.log(at, tag, message)
    s.task(f"{'vault':<7} unlocking /dev/vault0 using tpm-bound key ...", "OK", at=0.801544)
    s.task(f"{'vault':<7} verifying system image .......", "OK", at=1.120377)
    s.log(1.204910, "fs", "aefs vault0: mounted, journal clean")
    s.log(1.299410, "fs", "aefs vault0: 3 snapshots, last 2020-09-01")
    s.log(1.377002, "gate", "default policy drop (inbound)")
    s.log(1.402118, "audit", f"logging enabled, sink={CORE_HOST}")
    s.log(1.409300, "aek", "handing over to aeinit")
    s.blank()


def _units(s):
    s.say("aeinit  runlevel 3", style="dim")
    for name, description, result, note, ms in UNITS:
        label = f"{name:<10} "
        s.task(label + "starting", result, note, look="unit", done=label + description, ms=ms)
    s.wait((900, 1500))


def aether_boot(ident, *, short=False):
    s = Scene()
    _connect(s, ident)
    if not short:
        _firmware(s, ident)
        _bootloader(s)
        _kernel(s, ident)
    _units(s)
    s.cut()
    return s


# система машины -> загрузка (у других организаций будут свои)
BOOTS = {"AETHER": aether_boot}


def boot_scenes(ident, system="AETHER"):
    """Полная и короткая загрузка для страницы: {"full": [...], "short": [...]}."""
    build = BOOTS[system]
    return {"full": build(ident).to_dict(), "short": build(ident, short=True).to_dict()}
