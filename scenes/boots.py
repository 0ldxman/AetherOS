"""Загрузки машин: консольные сцены, что видит игрок на удалённой консоли.

У каждой операционной системы своя загрузка. Aether это не Linux и не его
стилизация: у системы своё ядро (aek), загрузчик (aeboot), инициализация (aeinit)
и контроллер управления (aemc). Всё пишется «по-настоящему» (подсистемы, время от
старта, проверки подписей, устройства), только на языке Aether. Тон холодный и
деловой: нижний регистр, выровненные колонки.

Aether работает на радио, поэтому у узла не ethernet, а радиомодем (rf0, rf1), антенна
и заземление. Данные машины (имя, hid, серийный номер, частота) берутся из
machines/world/identity.py, даты из machines/world/dates.py: загрузка и экран входа показывают одно
и то же железо и один и тот же мир (узел брошен, центр давно не отвечает).

Viper, Essig и Shroud получат свои функции рядом (у кого-то система может быть
старше, с пиксельным шрифтом и «настоящим» BIOS) и подключатся в BOOTS.

Полная загрузка: подключение, прошивка, загрузчик, ядро, службы. При повторном
заходе в рамках вкладки игроку показывают короткую: только подключение и службы.
"""
import hashlib

from scenes.engine import Scene
from machines.world.identity import CORE_HOST
from machines.world.dates import BEACON_LAST_SYNC, CORE_LAST_CONTACT, GAME_DATE, clearance_code, days_since

WIDTH = 12          # ширина подписей в таблицах прошивки

def _unit_groups(ident):
    """Службы aeinit по группам: (имя, описание, результат, длительность мс)."""
    return (
        ("base", (
            ("logd", "log daemon", "OK", (120, 400)),
            ("timesync", "clock synced from beacon (stratum 2)", "OK", (300, 800)),
            ("devd", "device manager, 14 devices", "OK", (150, 450)),
            ("entropyd", "entropy daemon, pool 4096 bits", "OK", (120, 350)),
            ("schedd", "job scheduler, 11 jobs", "OK", (150, 450)),
            ("keyagent", "secure key agent", "OK", (150, 500)),
            ("authd", "clearance daemon", "OK", (200, 600)),
            ("sessiond", "session broker", "OK", (150, 450)),
            ("compatd", "compatibility engine, 4,212 adapters", "OK", (500, 1200)),
        )),
        ("storage", (
            ("vaultd", "vault manager, 3 snapshots", "OK", (200, 600)),
            ("archive", "/archive mounted (read-only)", "OK", (250, 700)),
        )),
        ("radio", (
            ("rfd", f"radio daemon, rf0 locked at {ident.freq} MHz", "OK", (400, 900)),
            ("beacond", f"beacon directory stale, last sync {days_since(BEACON_LAST_SYNC)} d ago", "WARN", (500, 1100)),
            ("gate", "frame policy loaded, 214 rules", "OK", (250, 650)),
            ("linkd", "link supervisor, 1 of 2 radios active", "OK", (200, 550)),
            ("uplink", f"{CORE_HOST} unreachable, last contact {CORE_LAST_CONTACT}", "WARN", (1200, 2300)),
            ("telemetry", "7 of 12 sectors silent", "WARN", (700, 1300)),
        )),
        ("services", (
            ("relay", "message relay", "OK", (150, 500)),
            ("intercom", "mail service", "OK", (200, 550)),
            ("mapd", "map service", "OK", (200, 550)),
            ("aether-db", "knowledge base index", "OK", (400, 1000)),
            ("indexd", "search index, 3 collections", "OK", (250, 700)),
            ("notifyd", "notification bus", "OK", (150, 450)),
            ("archived", "archive service", "OK", (200, 600)),
            ("watcher", "legacy watcher exited (code 0x0f)", "FAIL", (300, 800)),
            ("desktop", "target reached", "OK", (250, 600)),
        )),
    )


# время от старта ядра (с), подсистема, текст
def _kernel_lines(ident):
    lines = [
        (0.000000, "aek", "aether kernel 5.8.14-hal (forge-03) #1 smp 2020-09-02"),
        (0.000000, "aek", "cmdline: vault=/dev/vault0 ro console=com1 quiet=2"),
        (0.000000, "aek", "mitigations: smep smap nx"),
        (0.001870, "efi", "boot services exited, memory map 38 entries"),
        (0.002400, "efi", "secure boot enabled, setup mode off"),
        (0.003100, "cpu", "mitigations: retpoline, stibp off"),
        (0.004211, "cpu", "AETHER QX-9, 8 cores, microcode 0x0a201009"),
        (0.004680, "cpu", "caches: l1 32k, l2 1m, l3 24m, smt on"),
        (0.006200, "cpu", "microcode revision 0x0a201009 loaded"),
        (0.007803, "mem", "64 GiB ecc, 4 channels, 0 errors"),
        (0.008900, "mem", "hugepages: 0 reserved"),
        (0.011302, "acpi", "tables ok (rsdp 0x00000000000f6a90)"),
        (0.012005, "timer", "tsc stable, clocksource tsc, 3.8 GHz"),
        (0.013600, "timer", "tsc calibrated 3800.012 MHz"),
        (0.014400, "irq", "apic enabled, 24 vectors routed"),
        (0.015900, "smp", "bringing up 7 secondary cores"),
        (0.016400, "sched", "scheduler: 8 cpus, 1 domain"),
        (0.017900, "rcu", "callback offloading on"),
        (0.018700, "smp", "8 cores online"),
        (0.019870, "pci", "0000:00 enumerated, 14 devices, 2 bridges"),
        (0.021300, "iommu", "enabled, 3 groups"),
        (0.022800, "pci", "0000:03:00.0 nvme controller"),
        (0.023400, "pci", "0000:05:00.0 radio controller (rf0)"),
        (0.024115, "nvme", "nvme0: AETHER-VAULT 4 TB, 1 namespace, queue depth 1024"),
        (0.026950, "usb", "xhci: 2 ports, no devices"),
        (0.028100, "hid", "keyboard, mouse: none attached"),
        (0.031440, "rf", f"rf0: hwid {ident.hid}, carrier {ident.freq} MHz, link up 38 Mbit/s"),
        (0.031902, "rf", "rf1: no carrier"),
        (0.033500, "rf", "rf0: ofdm 1024 carriers, fec ldpc 3/4, frame 1452"),
        (0.034100, "rf", "rf0: earth electrode 2.8 ohm, vswr 1.3"),
        (0.058230, "tpm", "tpm0: 2.0, pcr banks sha256, measured boot log 18 events"),
        (0.060100, "tpm", "tpm0: pcr 0-7 extended"),
        (0.071200, "aemc", "bmc channel up, console on com1"),
        (0.312874, "tamper", "chassis seal intact"),
        (0.314400, "tamper", "lid sensor ok"),
        (0.318002, "rng", "entropy pool seeded (hwrng)"),
        (0.322500, "crypto", "self-tests passed (chacha20, ed25519, sha256)"),
    ]
    return sorted(lines, key=lambda line: line[0])


def _pcr_digest(ident):
    return "sha256:" + hashlib.sha256((ident.hid + "pcr").encode()).hexdigest()[:32]


def _check(s, label, result):
    """Проверка прошивки: «label ........ result», результат зелёный."""
    s.task(f"{label:<20}", result, ms=(300, 800), style="success")


def _connect(s, ident):
    s.say("> ", end=False, cursor=True).type(f"aemc attach {ident.hostname}", speed=30)
    s.say("aemc 1.7  ·  management controller", style="dim")
    s.wait((200, 450))
    s.task("authenticating ", "OK", ms=(300, 700))
    s.task("opening channel ", "OK", ms=(500, 1100))
    s.say("console attached (escape: ~.)", style="dim")
    s.say("power state: on  ·  reset by remote request, 3 min ago", style="dim")
    s.say("requested by " + Scene.mask(10) + "  [restricted]", style="dim")
    s.wait((150, 350))
    s.task("waiting for console ", "OK", ms=(900, 1900))
    s.read()


def _firmware(s, ident):
    s.cut().wait((200, 400))
    s.say("AETHER FIRMWARE 2.4.1", ("  ·  uefi 2.8  ·  build 2020-02-18", "dim"))
    s.blank()
    s.row("node", ident.hostname, width=WIDTH)
    s.row("serial", ident.serial, width=WIDTH)
    s.blank()

    s.say("-- platform --", style="dim")
    s.row("cpu", "AETHER QX-9  8 cores  3.8 GHz", width=WIDTH)
    s.row("cache", "l1 32k  l2 1m  l3 24m", "dim", width=WIDTH)
    s.count("memory", 64, unit=" GiB", ms=(600, 1100), width=WIDTH, note="ecc, 4 channels")
    s.row("storage", "nvme0  AETHER-VAULT 4 TB  encrypted", width=WIDTH)
    s.row("", "nvme1  not present", "dim", width=WIDTH)
    s.say("radio".ljust(WIDTH), f"rf0 aether wideband 2-30 MHz  {ident.freq} MHz locked")
    s.say(" " * WIDTH, "rf1 ", ("no carrier", "warning"))
    s.row("antenna", "loop 40 m  vswr 1.3", "dim", width=WIDTH)
    s.row("earth", "electrode 2.8 ohm", "dim", width=WIDTH)
    s.row("hwid", ident.hid, "dim", width=WIDTH)
    s.row("date", f"{GAME_DATE}  03:12:08 UTC  (beacon)", "dim", width=WIDTH)
    s.row("bmc", "aemc 1.7  online", width=WIDTH)
    s.row("pci", "14 devices, 2 bridges", "dim", width=WIDTH)
    s.row("boot order", "nvme0, radio (disabled)", "dim", width=WIDTH)
    s.wait((200, 400)).blank()

    s.say("-- security --", style="dim")
    _check(s, "secure boot", "enabled")
    _check(s, "tpm 2.0", "present")
    _check(s, "measured boot", "sealed")
    s.row("pcr 0-7", _pcr_digest(ident), "dim", width=WIDTH)
    _check(s, "firmware signature", "verified")
    _check(s, "chassis intrusion", "none")
    _check(s, "boot keys (db)", "3 loaded")
    s.blank()

    s.say("-- self test --", style="dim")
    _check(s, "cpu", "8 of 8 cores")
    _check(s, "memory (quick)", "pass")
    _check(s, "nvme0 smart", "ok, 0 media errors")
    _check(s, "rf0 loopback", "pass")
    _check(s, "earth bond", "2.8 ohm")
    s.task(f"{'rf1 loopback':<20}", "skipped, no carrier", style="warning", ms=(300, 700))
    s.read()


def _bootloader(s):
    s.cut()
    s.say("AEBOOT 2.1", ("  ·  signed loader", "dim"))
    s.blank()
    s.row("entry", "aether 9.1 (halcyon)", note="default", width=WIDTH)
    s.row("kernel", "aek 5.8.14-hal  vault=/dev/vault0", "dim", width=WIDTH)
    s.say("recovery".ljust(WIDTH), ("aether 9.1 recovery  ", "dim"), (f"[clearance {clearance_code(5)} required]", "error"))
    s.say("diagnostics".ljust(WIDTH), ("memory, vault  ", "dim"), ("[locked]", "warning"))
    s.blank()
    s.bar("loading aek 5.8.14-hal   ", ms=(900, 1600))
    s.task("verifying image signature ", "OK", ms=(400, 800))
    s.task("measuring into pcr 8-9 ", "OK", ms=(200, 500))
    s.row("handoff", "aek entry 0xffffffff81000000", "dim", width=WIDTH)
    s.read()


def _kernel(s, ident):
    s.cut()
    for at, tag, message in _kernel_lines(ident):
        s.log(at, tag, message)
    s.task(f"{'vault':<7} unlocking /dev/vault0 using tpm-bound key ...", "OK", at=0.801544)
    s.task(f"{'vault':<7} verifying system image .......", "OK", at=1.120377)
    s.log(1.204910, "fs", "aefs vault0: mounted, journal clean")
    s.log(1.299410, "fs", f"aefs vault0: 3 snapshots, last {CORE_LAST_CONTACT}")
    s.log(1.340200, "sec", "policy loaded: 214 rules, default deny")
    s.log(1.377002, "gate", "default policy drop (inbound)")
    s.log(1.402118, "audit", f"logging enabled, sink {CORE_HOST} unreachable, buffering to vault")
    s.log(1.409300, "aek", "handing over to aeinit")
    s.blank()


def _units(s, ident):
    s.say("aeinit  runlevel 3", style="dim")
    for group, units in _unit_groups(ident):
        s.say(f"-- {group} --", style="dim")
        for name, description, result, ms in units:
            label = f"{name:<10} "
            s.task(label + "starting", result, look="unit", done=label + description, ms=ms)
    s.read(min_ms=1200)


def aether_boot(ident, *, short=False):
    s = Scene()
    _connect(s, ident)
    if not short:
        _firmware(s, ident)
        _bootloader(s)
        _kernel(s, ident)
    _units(s, ident)
    s.cut()
    return s


# система машины -> загрузка (у других организаций будут свои)
BOOTS = {"AETHER": aether_boot}


def boot_scenes(ident, system="AETHER"):
    """Полная и короткая загрузка для страницы: {"full": [...], "short": [...]}."""
    build = BOOTS[system]
    return {"full": build(ident).to_dict(), "short": build(ident, short=True).to_dict()}
