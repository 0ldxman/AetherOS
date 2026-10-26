"""Сцены моста: соединение с другой машиной, отказ, закрытие и обрыв.

Вид зависит от системы целевой машины: Aether это радио (частота, несущая, обмен ключами), любая другая система
говорит на обычном сетевом языке (порт, tcp, tls). Сцену собирает сервер уже после решения: в неё попадает
только то, что игрок и так узнал бы из ответа.
"""
from console.scene import Scene

AETHER = "AETHER"


def _endpoint(system, profile):
    """Частота у Aether, порт у остальных."""
    if system == AETHER:
        return f"{profile.freq:.3f} MHz"
    return str(int(profile.freq))


def connect_scene(system, host, profile, cut=True, opened=True):
    """Игрок вошёл: соединение, обмен ключами, вход, и (cut) чёрный кадр перед сменой рабочего стола.
    rshell и xfer не меняют рабочий стол: для них cut=False, а xfer ещё и не говорит об открытой сессии."""
    s = Scene()
    if system == AETHER:
        s.task(f"resolving  {host} ", "OK", ms=(200, 450))
        s.task(f"tuning     rf0 {_endpoint(system, profile)} ", "OK", ms=(500, 1100))
        s.task("carrier    locked ", "OK", ms=(300, 700))
        s.bar("key exchange ", ms=(700, 1300), width=20)
        s.task(f"auth       {profile.login} ", "OK", ms=(300, 700))
    else:
        s.task(f"resolving  {host} ", "OK", ms=(150, 350))
        s.task(f"connect    {host}:{_endpoint(system, profile)} ", "OK", ms=(250, 600))
        s.task("tls        handshake ", "OK", ms=(300, 700))
        s.task(f"auth       {profile.login} ", "OK", ms=(250, 600))
    if opened:
        s.say("session opened.", style="success")
    if cut:
        s.wait(450).cut()
    return s.to_dict()


def denied_scene(system, host, login, endpoint=None):
    """Соединение дошло, но вход не принят."""
    s = Scene()
    if system == AETHER:
        s.task(f"resolving  {host} ", "OK", ms=(200, 450))
        s.task(f"tuning     rf0 {endpoint or 'scan'} ", "OK", ms=(400, 900))
        s.bar("key exchange ", ms=(600, 1100), width=20)
    else:
        s.task(f"resolving  {host} ", "OK", ms=(150, 350))
        s.task("tls        handshake ", "OK", ms=(300, 700))
    s.task(f"auth       {login} ", "FAIL", ms=(500, 1100))
    return s.to_dict()


def unreachable_scene(system, host):
    """Такой машины нет."""
    s = Scene()
    s.task(f"resolving  {host} ", "FAIL", ms=(500, 1100))
    return s.to_dict()


def disconnect_scene(system, host, cut=True):
    """Мост (или оболочка, тогда cut=False: рабочий стол не меняется) закрыт: возвращаемся на уровень выше."""
    s = Scene()
    s.task("session    closing ", "OK", ms=(250, 550))
    s.say(f"connection to {host} closed.", style="dim")
    if cut:
        s.wait(350).cut()
    return s.to_dict()


def transfer_scene(name, size_seed, ok=True, connect=None):
    """Перенос файла: открытие канала, полоса передачи, проверка. connect это сцена соединения (xfer с явным адресом)."""
    from terminal.scenes import _stable, _result

    s = Scene()
    for step in (connect or []):
        s.steps.append(step)
    s.task("channel    opening ", "OK", ms=(150, 350))
    s.count(f"sending {name} ", _stable(name + str(size_seed), 4, 900), unit=" KB", ms=(500, 1100), width=12)
    s.task("checksum   ", _result(ok), ms=(250, 550))
    return s.to_dict()


def kick_scene(system, host):
    """Игрока выбросило: связь оборвали с той стороны."""
    s = Scene()
    s.wait(250)
    s.say(f"connection to {host} lost: reset by peer", style="error")
    s.wait(900).cut()
    return s.to_dict()
