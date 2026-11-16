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


def drops(machine, seconds, rng=random):
    """Оборвётся ли подключение за seconds секунд работы с машиной (шанс drop_pct % за минуту)."""
    rate = min(100.0, max(0.0, float(getattr(machine, "drop_pct", 0) or 0))) / 100
    if not rate or seconds <= 0:
        return False
    return rng.random() < 1 - (1 - rate) ** (min(seconds, CAP) / 60)
