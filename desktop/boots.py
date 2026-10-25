"""Загрузки машин: консольные сцены, что видит игрок на удалённой консоли.

У каждой операционной системы своя загрузка. Aether (альтернативный 2020 год,
технологии почти как у нас) загружается так, как ниже: консоль управления,
прошивка UEFI с проверкой подписей, загрузчик, ядро, службы. Тон холодный и
деловой: нижний регистр, выровненные колонки, без анимации ради анимации.

Viper, Essig и Shroud получат свои функции рядом (у кого-то система может быть
старше, с пиксельным шрифтом и «настоящим» BIOS) и подключатся в BOOTS.

Полная загрузка: подключение, прошивка, загрузчик, ядро, службы. При повторном
заходе в рамках вкладки игроку показывают короткую: только подключение и службы.
"""
import random

from console.scene import Scene

NODE = "NODE-07"
DOMAIN = "AETHER"
SERIAL = "AE-0007-4471-C"
PCR_DIGEST = "sha256:9c1e44a0b73d08f2e5a163cc7d20"
WIDTH = 12          # ширина подписей в таблицах прошивки

# (пока запускается, запущено, результат, пояснение)
SERVICES = (
    ("Starting Secure Key Agent...", "Started Secure Key Agent.", "OK", None),
    ("Starting Clearance Daemon (aetherd-auth)...", "Started Clearance Daemon (aetherd-auth).", "OK", None),
    ("Mounting /archive...", "Mounted /archive", "OK", " (read-only)."),
    (f"Starting Uplink to NODE-00.{DOMAIN}...", f"Started Uplink to NODE-00.{DOMAIN}.", "OK", None),
    ("Checking sector telemetry...", "Sector 12 telemetry: no response, skipping.", "WARN", None),
    ("Starting Message Relay...", "Started Message Relay.", "OK", None),
    ("Starting Archive Service...", "Started Archive Service.", "OK", None),
    ("Starting Legacy Watcher...", "Failed to start Legacy Watcher (code 0x0F).", "FAIL", None),
    ("Reaching target Aether Desktop...", "Reached target Aether Desktop.", "OK", None),
)


def _check(s, label, result):
    """Проверка прошивки: «label ........ result», результат зелёный."""
    s.task(f"{label:<20}", result, ms=550, style="success")


def _connect(s):
    host = f"{NODE}.{DOMAIN}".lower()
    s.say("> ", end=False).type(f"sol connect {host}", speed=30)
    s.wait(400)
    s.task("establishing channel ", "OK", ms=900)
    s.say("sol session opened (escape: ~.)", style="dim")
    s.wait(300)
    s.task("waiting for console ", "OK", ms=1500)


def _firmware(s):
    s.clear().wait(300)
    s.say("AETHER FIRMWARE 2.4.1", ("  ·  uefi 2.8  ·  build 2020-02-18", "dim"))
    s.blank()
    s.row("node", NODE, width=WIDTH)
    s.row("serial", SERIAL, width=WIDTH)
    s.blank()

    s.say("-- platform --", style="dim")
    s.row("cpu", "AETHER QX-9  8 cores  3.8 GHz", width=WIDTH)
    s.count("memory", 64, unit=" GiB", ms=900, width=WIDTH, note="ecc, 4 channels")
    s.row("storage", "nvme0  AETHER-VAULT 4 TB  encrypted", width=WIDTH)
    s.say("network".ljust(WIDTH), "eth0 10 Gbps up   eth1 ", ("no carrier", "warning"))
    s.wait(300).blank()

    s.say("-- security --", style="dim")
    _check(s, "secure boot", "enabled")
    _check(s, "tpm 2.0", "present")
    _check(s, "measured boot", "sealed")
    s.row("pcr 0-7", PCR_DIGEST, "dim", width=WIDTH)
    _check(s, "firmware signature", "verified")
    s.wait(800)


def _bootloader(s):
    s.clear()
    s.say("AETHER BOOT", ("  ·  signed loader 2.1", "dim"))
    s.blank()
    s.row("entry", "aether-os 9.1 (halcyon)", note="default", width=WIDTH)
    s.say("recovery".ljust(WIDTH), ("aether-os 9.1 recovery  ", "dim"), ("[clearance L5 required]", "error"))
    s.blank()
    s.bar("loading kernel   ", ms=1300)
    s.task("verifying image signature ", "OK", ms=600)
    s.wait(500)


def _kernel(s):
    s.clear()
    s.log(0.0, "aether-kernel 5.8.14-hal (builder@forge-03) #1 SMP 2020-09-02")
    s.log(0.0, "Command line: root=/dev/vault0 ro console=ttyS0 quiet_level=2")
    s.log(0.004211, "CPU: AETHER QX-9, 8 cores, microcode 0x0a201009")
    s.log(0.312874, "tamper: chassis seal intact")
    s.task("vault: unlocking /dev/vault0 using TPM-bound key ...", "OK", at=0.801544)
    s.task("integrity: verifying system image .......", "OK", at=1.120377)
    s.log(1.204910, "AEFS (vault0): mounted, journal clean")
    s.log(1.377002, "netfilter: default policy DROP (inbound)")
    s.log(1.402118, f"audit: logging enabled, sink=NODE-00.{DOMAIN}")
    s.blank()


def _services(s):
    for pending, done, result, note in SERVICES:
        s.task(pending, result, note, look="service", done=done, ms=random.randint(300, 700))
    s.wait(1200)


def aether_boot(*, short=False):
    s = Scene()
    _connect(s)
    if not short:
        _firmware(s)
        _bootloader(s)
        _kernel(s)
    _services(s)
    s.fade("out", 500)
    return s


# система машины -> загрузка (у других организаций будут свои)
BOOTS = {"AETHER": aether_boot}


def boot_scenes(system="AETHER"):
    """Полная и короткая загрузка для страницы: {"full": [...], "short": [...]}."""
    build = BOOTS[system]
    return {"full": build().to_dict(), "short": build(short=True).to_dict()}
