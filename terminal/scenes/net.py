"""Сцены сетевых команд (nreq, nget). Вид зависит от системы машины игрока: у Aether это радио, у остальных обычная сеть."""
from scenes.engine import Scene

AETHER = "AETHER"


def _reach(s, system, address):
    if system == AETHER:
        s.task(f"tuning     {address} ", "OK", ms=(300, 800))
        s.task("carrier    locked ", "OK", ms=(250, 600))
    else:
        s.task(f"resolving  {address} ", "OK", ms=(150, 350))
        s.task("connect    ", "OK", ms=(250, 600))


def request_scene(system, address):
    s = Scene()
    _reach(s, system, address)
    s.task("response   ", "OK", ms=(250, 600))
    return s.to_dict()


def download_scene(system, address, name):
    s = Scene()
    _reach(s, system, address)
    s.bar(f"receiving {name} ", ms=(800, 1600), width=20)
    s.task("checksum   ", "OK", ms=(250, 550))
    return s.to_dict()


def unreachable_scene(system, address):
    s = Scene()
    s.task(f"{'tuning' if system == AETHER else 'resolving'}  {address} ", "FAIL", ms=(500, 1100))
    return s.to_dict()


def refused_scene(system, address):
    s = Scene()
    _reach(s, system, address)
    s.task("response   ", "FAIL", ms=(250, 600))
    return s.to_dict()
