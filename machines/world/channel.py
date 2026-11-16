"""Канал до машины: медленный (задержка ответа терминала) и нестабильный (помехи в выводе, обрывы подключения).

Помехи — как на настоящей линии: сбитый бит превращает латинский символ в соседний по коду (a → c, / → ?), порченый байт многобайтного
символа (кириллица в UTF-8) даёт �, байт может пропасть или повториться. Каждый ответ портится заново: повтор команды помогает
восстановить текст."""
import random

LAG = {"light": (500, 1200, 60), "heavy": (2000, 4000, 180)}         # пауза до ответа, мс (от, до) и пауза между строками
NOISE = {"rare": 0.012, "often": 0.04}                               # доля испорченных символов
DROP = {"rare": 0.03, "often": 0.1}                                  # вероятность обрыва на команду
SLOW_COMMANDS = {"xfer": 3}                                          # во сколько раз дольше


def delay(machine, command="", rng=random):
    """(пауза до ответа, пауза между строками) в мс или (0, 0)."""
    found = LAG.get(getattr(machine, "lag", "none"))
    if not found:
        return 0, 0
    low, high, line = found
    times = SLOW_COMMANDS.get(command, 1)
    return int(rng.uniform(low, high) * times), line


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
    rate = NOISE.get(getattr(machine, "noise", "none"))
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


def drops(machine, rng=random):
    """Оборвётся ли подключение на этой команде."""
    rate = DROP.get(getattr(machine, "noise", "none"))
    return bool(rate) and rng.random() < rate
