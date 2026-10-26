"""Сцены терминала: анимация вокруг ответа команды и приветствие оболочки.

Это тот же язык, что у загрузки и входа (console/scene.py). Сцена только показывает работу команды;
решение (слой снят или нет) принимает сервер раньше и кладёт его в сцену как готовый результат. Текст ответа
остаётся обычным и печатается после сцены. В сцену, как и в ответ, попадает только то, что игрок уже вправе видеть.
"""
import hashlib

from console.scene import Scene
from users.gateway import _motd


def _stable(seed, low, high):
    """Число от low до high, у одного seed всегда одно и то же (размер «файла» не прыгает между запусками)."""
    value = int.from_bytes(hashlib.sha256(str(seed).encode()).digest()[:4], "big")
    return low + value % (high - low + 1)


def _result(ok):
    return "OK" if ok else "FAIL"


# ---------- снятие слоёв ----------

def _encrypted(s, path, ok):
    s.task("reading header", "OK", ms=(180, 380))
    s.bar("deriving key ", ms=(700, 1300), width=20)
    s.task("checking passphrase", _result(ok), ms=(350, 800))


def _base64(s, path, ok):
    s.task("decoding", _result(ok), ms=(250, 650))


def _archive(s, path, ok):
    s.count("reading index", _stable(path, 4, 60), unit=" entries", ms=(400, 800), width=10)
    s.bar("unpacking ", ms=(700, 1300), width=20)
    s.task("verifying", _result(ok), ms=(250, 550))


def _binary(s, path, ok):
    s.count("scanning", _stable(path, 400, 9000), unit=" bytes", ms=(500, 1000), width=10)
    s.task("collecting strings", _result(ok), ms=(300, 700))


def _shifted(s, path, ok):
    s.task("seeking", "OK", ms=(200, 450))
    s.bar("reading ", ms=(500, 1000), width=20)
    s.task("block check", _result(ok), ms=(250, 550))


def _disguised(s, path, ok):
    s.task("probing format", "OK", ms=(250, 500))
    s.bar("converting ", ms=(600, 1200), width=20)
    s.task("validating", _result(ok), ms=(250, 600))


def _generic(s, path, ok):
    s.task("working", _result(ok), ms=(300, 800))


_UNLOCK = {"encrypted": _encrypted, "base64": _base64,
           "archive": _archive, "binary": _binary, "shifted": _shifted, "disguised": _disguised}


def unlock_scene(layer, path, ok):
    """Работа команды, снимающей слой файла: ok это уже принятое сервером решение."""
    scene = Scene()
    _UNLOCK.get(layer, _generic)(scene, path, ok)
    return scene.to_dict()


def repair_scene(path, size, ok, more):
    """Восстановление файла (rpr): проходы как у fsck и ddrescue, а восстановление блоков идёт сразу по всем плохим,
    каждый со своим темпом. more значит, что под снятым слоем лежит ещё один damaged: часть блоков за этот проход не
    поддаётся (их полоса встаёт и кончается FAIL). Сервер уже решил исход (ok, more)."""
    blocks = max(8, -(-size // 512))
    bad = min(blocks - 1, _stable(path, 3, 9))
    lost = _stable(path + ":rest", 1, max(1, bad // 2)) if more else 0

    numbers, index = [], 0
    while len(numbers) < bad:
        number = _stable(f"{path}:{index}", 0, blocks - 1)
        index += 1
        if number not in numbers:
            numbers.append(number)
    numbers.sort()

    order = sorted(range(bad), key=lambda i: _stable(f"{path}:o{i}", 0, 10**6))
    failing = set(order[:lost])
    rows = []
    for i, number in enumerate(numbers):
        start = 900 + _stable(f"{path}:t{i}", 0, 1800)          # у каждого блока свой темп
        row = (f"  block {number:05d} ", (start, start + 600))
        rows.append(row + (("FAIL", 35 + _stable(f"{path}:s{i}", 0, 50)) if i in failing else ()))

    s = Scene()
    s.row("rpr", path, width=8)
    s.row("size", f"{size} bytes", note=f"{blocks} blocks of 512", width=8)
    s.blank()
    s.count("pass 1/4  surface scan", blocks, unit=" blk", ms=(min(2600, 500 + blocks * 9), min(3200, 800 + blocks * 12)), width=26)
    s.say(f"  {bad} damaged blocks", style="warning")
    s.task("pass 2/4  rebuilding block map", "OK", ms=(500, 1000))
    s.say("pass 3/4  reconstructing from parity")
    s.bars(rows, width=14)
    s.say(f"  recovered {bad - lost} of {bad} blocks", style="warning" if lost else "dim")
    s.task("pass 4/4  verifying checksums", "FAIL" if not ok else ("WARN" if more else "OK"), ms=(400, 800))
    return s.to_dict()           # вердикт (repaired, further repair required) говорит ответ команды


# ---------- сырые байты ----------

def block_scene(path, blocks):
    """blk: перемотка и чтение блоков (dd). Работы тем больше, чем больше блоков."""
    s = Scene()
    s.task("seeking", "OK", ms=(60, 160))
    if blocks:
        s.task(f"reading {blocks} block{'s' if blocks != 1 else ''}", "OK", ms=(80 * blocks, 140 * blocks))
    return s.to_dict()


def strings_scene(path, size):
    """txtx: просмотр байтов в поисках читаемого."""
    s = Scene()
    s.count("scanning", size, unit=" B", ms=(150, 450), width=10)
    return s.to_dict()


def convert_scene(path, size, value, ok, kind):
    """cvt: чтение файла как названного формата (disguised) или раскодирование кодировки (binary). Решение уже принято
    сервером: неверное название обрывается на разборе входа, и по сцене ничего не узнать раньше ответа."""
    stage = "input" if kind == "disguised" else "stream"
    s = Scene()
    s.row("cvt", path, width=8)
    s.row("size", f"{size} bytes", width=8)
    s.row(stage, f"{value}", note="read as requested" if kind == "disguised" else "decode as requested", width=8)
    s.blank()
    s.task("probing input", "OK" if ok else "FAIL", ms=(500, 1100))
    if not ok:
        return s.to_dict()
    if kind == "disguised":
        s.row("  pages", str(_stable(path + ":pg", 1, 40)), width=10)
        s.row("  objects", str(_stable(path + ":ob", 60, 900)), width=10)
    else:
        s.row("  units", str(max(1, size // 2)), width=10)
    s.bar("decoding streams ", ms=(900, 1800), width=14)
    s.task("writing output", "OK", ms=(300, 700))
    return s.to_dict()


# ---------- просмотр файла ----------

def ftyp_scene(path):
    """Определение типа смотрит только заголовок и потому быстрое. Одинаковая для любого файла: по ней ничего не узнать
    раньше ответа."""
    s = Scene()
    s.task("reading header", "OK", ms=(60, 160))
    return s.to_dict()


def open_scene(path, stage):
    """Открытие содержимого. stage говорит, где оно остановилось (решение принято сервером раньше): access (доступ
    закрыт слоем), content (открывать нечего), opened (окно открылось). Читать данных тут нет: окно читает их само."""
    s = Scene()
    s.task("checking access", "FAIL" if stage == "access" else "OK", ms=(120, 300))
    if stage != "access":
        s.task("locating content", "FAIL" if stage == "content" else "OK", ms=(120, 280))
    if stage == "opened":
        s.task("launching viewer", "OK", ms=(200, 450))
    return s.to_dict()


# ---------- корзина ----------

def trash_scene(count):
    s = Scene()
    s.task("moving to trash", "OK", ms=(150, 400))
    return s.to_dict()


def recover_scene(path):
    s = Scene()
    s.count("scanning trash", _stable(path, 120, 1800), unit=" blocks", ms=(500, 1000), width=10)
    s.bar("recovering ", ms=(700, 1400), width=20)
    s.task("checksum", "WARN", ms=(250, 550))
    return s.to_dict()


def wipe_scene(count):
    s = Scene()
    s.bar("overwriting ", ms=(500, 1100), width=20)
    s.task("trash emptied", "OK", ms=(150, 350))
    return s.to_dict()


# ---------- приветствие ----------

def greeting_scene(ident, login, mail=None):
    """Оболочка открылась: шапка сеанса, то же приветствие узла, что после входа (логотип, нагрузка, радио,
    уведомления, последний вход, почта) и подсказка. Каждое окно терминала начинается так; любая клавиша доигрывает."""
    s = Scene()
    s.say(f"aether-shell 1.4 on {ident.hostname}", style="dim")
    s.task("pty       allocating 120x32 ", "OK", ms=(150, 320))
    s.task("env       TERM=aether-256 ", "OK", ms=(120, 260))
    s.task(f"session   {login} ", "OK", ms=(180, 360))
    s.say("recording on", style="dim")
    _motd(s, ident, login, mail, read=False)
    s.say("  Type ", ("ls", "success"), " to look around, ", ("clear", "success"), " to wipe the screen.", style="dim")
    s.blank()
    return s.to_dict()
