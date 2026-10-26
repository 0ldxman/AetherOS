"""Сцены терминала: анимация вокруг ответа команды и приветствие оболочки.

Это тот же язык, что у загрузки и входа (console/scene.py). Сцена только показывает работу команды;
решение (слой снят или нет) принимает сервер раньше и кладёт его в сцену как готовый результат. Текст ответа
остаётся обычным и печатается после сцены. В сцену, как и в ответ, попадает только то, что игрок уже вправе видеть.
"""
import hashlib

from console.scene import Scene
from users.gateway import _mail_line


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


def _generic(s, path, ok):
    s.task("working", _result(ok), ms=(300, 800))


_UNLOCK = {"encrypted": _encrypted, "base64": _base64, "damaged": _damaged}


def unlock_scene(layer, path, ok):
    """Работа команды, снимающей слой файла: ok это уже принятое сервером решение."""
    scene = Scene()
    _UNLOCK.get(layer, _generic)(scene, path, ok)
    return scene.to_dict()


# ---------- приветствие ----------

def greeting_scene(ident, login, mail=None):
    """Оболочка открылась: короткая строка о сеансе и почта. Каждое окно терминала начинается так."""
    s = Scene()
    s.say(f"aether-shell 1.4 on {ident.hostname}  (pty0)", style="dim")
    s.say("session  ", (login, "success"), ("  ·  recording on", "dim"))
    _mail_line(s, mail)
    s.blank()
    return s.to_dict()
