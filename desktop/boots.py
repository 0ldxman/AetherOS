"""Загрузки машин: консольные сцены, что видит игрок на удалённой консоли.

У каждой операционной системы своя загрузка. Aether загружается так, как ниже;
Viper, Essig и Shroud получат свои функции рядом и подключатся в BOOTS.

Полная загрузка: подключение, BIOS, загрузчик, ядро, службы. При повторном заходе
в рамках вкладки игроку показывают короткую: только подключение и службы.
"""
import random

from console.scene import Scene

NODE = "NODE-07"
DOMAIN = "AETHER"
SERIAL = "AE-0007-4471-C"
MEMORY_KB = 67_108_864

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


def _connect(s):
    s.say("> ", end=False).type(f"CONNECT {NODE}.{DOMAIN}", speed=30)
    s.wait(400)
    s.task("Establishing secure channel ", "OK", ms=900, style="success")
    s.type("Serial-over-LAN session opened. Escape sequence: ~.", speed=15, style="dim")
    s.wait(300)
    s.task("Waiting for remote console ", "OK", ms=1800)


def _bios(s):
    s.clear().wait(300)
    s.say("AETHER-BIOS v4.12.0  (C) 2061 Aether Dynamics Consortium")
    s.say(f"Node: {NODE}   Serial: {SERIAL}")
    s.say("Build: 2061-03-14 / secure-boot chain v3")
    s.wait(300).blank()

    s.say("CPU0: AETHER QX-9 Quantum-Assisted   8 cores   3.80 GHz")
    s.wait(300)
    s.count("Memory Testing:", MEMORY_KB, unit="K", result="OK", note="(ECC, quad channel)")
    s.wait(300)
    s.row("Chipset:", "AETHER Nexus-Q2", width=17)
    s.wait(300)
    s.task("Crypto module:  TPM-X 3.0 ", "PRESENT", ms=1800, style="success")
    s.wait(300)
    s.task("Tamper seal:    ", "INTACT", ms=1800, style="success")
    s.wait(300).blank()

    s.say("Primary Storage Master:  AETHER-VAULT 4TB (encrypted)")
    s.wait(300)
    s.say("Primary Storage Slave:   ", ("None", "dim"))
    s.wait(300)
    s.say("Network uplink:          ETH0 UP 10Gbps   ETH1 NO CARRIER")
    s.wait(300).blank()

    s.task("Verifying firmware signature ", "OK", ms=1800)
    s.blank()
    s.say("Press <DEL> for SETUP, <F12> for boot menu", style="dim")
    s.wait(1000)


def _boot_manager(s):
    s.clear()
    s.say("AETHER BOOT MANAGER 2.12")
    s.wait(1000).blank()
    s.say("> AETHER OS 9.1 (Halcyon)")
    s.say(("  AETHER OS 9.1 (Halcyon) - recovery mode      ", "dim"), ("[CLEARANCE L5 REQUIRED]", "error"))
    s.say("  AETHER OS 8.4 (legacy)", style="dim")
    s.say("  Memory diagnostic", style="dim")
    s.blank()
    s.countdown("Auto-boot in {n}s...", 3)
    s.flash()


def _kernel(s):
    s.clear()
    s.log(0.0, "Aether kernel 9.1.4-hal (builder@forge-03) #1 SMP 2061-03-02")
    s.log(0.0, "Command line: root=/dev/vault0 ro console=ttyS0 quiet_level=2")
    s.log(0.004211, "CPU: detected AETHER QX-9, 8 cores, quantum coprocessor online")
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
        _bios(s)
        _boot_manager(s)
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
