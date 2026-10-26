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


def _damaged(s, path, ok):
    s.count("scanning", _stable(path, 180, 2400), unit=" blocks", ms=(600, 1100), width=10)
    s.bar("rebuilding ", ms=(800, 1500), width=20)
    s.task("checksum", _result(ok), ms=(250, 550))


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


_UNLOCK = {"encrypted": _encrypted, "base64": _base64, "damaged": _damaged,
           "archive": _archive, "binary": _binary, "shifted": _shifted, "disguised": _disguised}


def unlock_scene(layer, path, ok):
    """Работа команды, снимающей слой файла: ok это уже принятое сервером решение."""
    scene = Scene()
    _UNLOCK.get(layer, _generic)(scene, path, ok)
    return scene.to_dict()


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
