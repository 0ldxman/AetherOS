"""Канал до машины: медленный (задержка ответа терминала) и нестабильный (помехи в выводе, обрывы подключения).

Помехи — как на настоящей линии: сбитый бит превращает латинский символ в соседний по коду (a → c, / → ?), порченый байт многобайтного
символа (кириллица в UTF-8) даёт �, байт может пропасть или повториться. Каждый ответ портится заново: повтор команды помогает
восстановить текст. Обрывы считаются по времени работы с машиной (bridge.mark_seen), а не по командам."""
import random

JITTER = 0.3                         # задержка гуляет на ±30%
SLOW_COMMANDS = {"xfer": 3}          # во сколько раз дольше
CAP = 120                            # больше стольких секунд без запросов за раз не считается работой


def delay(machine, command="", rng=random):
    """(пауза до ответа, пауза между строками) в мс или (0, 0)."""
    base = int(getattr(machine, "lag_ms", 0) or 0)
    if base <= 0:
        return 0, 0
    pause = base * rng.uniform(1 - JITTER, 1 + JITTER) * SLOW_COMMANDS.get(command, 1)
    return int(pause), max(20, min(250, base // 15))


def _flip(char, rng):
    code = ord(char)
    if code > 126:
        return "\ufffd"                                               # порченый байт многобайтного символа
    for _ in range(8):
        flipped = code ^ (1 << rng.randrange(6))
        if 32 <= flipped <= 126:
            return chr(flipped)
    return char


def garble(text, machine, rng=random):
    """Вывод через нестабильный канал: часть символов сбита, пропала или повторилась. Переводы строк не трогаются."""
    rate = min(100.0, max(0.0, float(getattr(machine, "noise_pct", 0) or 0))) / 100
    if not rate or not text:
        return text
    out = []
    for char in text:
        if char in "\n\r" or rng.random() >= rate:
            out.append(char)
            continue
        roll = rng.random()
        if roll < 0.75:
            out.append(_flip(char, rng))
        elif roll < 0.88:
            continue                                                 # байт потерялся
        else:
            out.append(char + char)                                  # байт повторился
    return "".join(out)


def _pct(machine, name):
    return min(100.0, max(0.0, float(getattr(machine, name, 0) or 0))) / 100


def overloaded(machine, command="", rng=random):
    """Не выполнилась ли команда из-за перегрузки (выход из оболочки работает всегда)."""
    rate = _pct(machine, "overload_pct")
    return bool(rate) and command not in ("exit", "rcon-close", "") and rng.random() < rate


def transfer_ms(size, *machines):
    """Сколько мс идёт передача size байт по самому узкому каналу из machines (0 — ограничения нет)."""
    limits = [int(getattr(machine, "bandwidth_kbps", 0) or 0) for machine in machines if machine is not None]
    limits = [kbps for kbps in limits if kbps > 0]
    return int(size / 1024 / min(limits) * 1000) if limits else 0


def damaged(size, *machines, rng=random):
    """Пришёл ли файл size байт испорченным: каждый блок 4 КБ портится с вероятностью помех канала."""
    rate = max((_pct(machine, "noise_pct") for machine in machines if machine is not None), default=0)
    if not rate:
        return False
    blocks = max(1, -(-int(size) // 4096))
    return rng.random() < min(0.95, 1 - (1 - rate) ** blocks)


def drops(machine, seconds, rng=random):
    """Оборвётся ли подключение за seconds секунд работы с машиной (шанс drop_pct % за минуту)."""
    rate = min(100.0, max(0.0, float(getattr(machine, "drop_pct", 0) or 0))) / 100
    if not rate or seconds <= 0:
        return False
    return rng.random() < 1 - (1 - rate) ** (min(seconds, CAP) / 60)
