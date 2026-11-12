"""Шифр эфира: Виженер по латинице и кириллице отдельно, цифры, пробелы и знаки как есть.

Передача с ключом уходит шифровкой. Слушатель с ключом расшифровывает своим ключом всё, что слышит: тот же ключ даёт
открытый текст, чужое и открытое превращается в кашу. Без ключа шифровка видна как есть. Вскрывается частотным анализом,
как и задумано: ключ ищут в мире.
"""
import hashlib

LATIN = "abcdefghijklmnopqrstuvwxyz"
CYRILLIC = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
MAX_KEY = 32


def _shifts(key):
    """Сдвиги по буквам ключа: буква даёт свой номер в своём алфавите, цифра — себя; прочее пропускается."""
    out = []
    for char in (key or "").lower():
        if char in LATIN:
            out.append(LATIN.index(char))
        elif char in CYRILLIC:
            out.append(CYRILLIC.index(char))
        elif char.isdigit():
            out.append(int(char))
    return out


def normalize(key):
    """Ключ как его хранит приёмник: без пробелов по краям, до 32 знаков; пусто — без ключа. Регистр не важен."""
    key = " ".join((key or "").split())[:MAX_KEY]
    return key if _shifts(key) else ""


def mark(key):
    """Отпечаток ключа: совпадает у одинаковых ключей (без учёта регистра), пусто для «без ключа»."""
    key = normalize(key).lower()
    return hashlib.sha256(f"air:{key}".encode()).hexdigest()[:16] if key else ""


def _run(text, key, sign):
    shifts = _shifts(key)
    if not shifts:
        return text
    out, step = [], 0
    for char in text:
        lower = char.lower()
        alphabet = LATIN if lower in LATIN else CYRILLIC if lower in CYRILLIC else None
        if alphabet is None:
            out.append(char)
            continue
        shifted = alphabet[(alphabet.index(lower) + sign * shifts[step % len(shifts)]) % len(alphabet)]
        out.append(shifted.upper() if char != lower else shifted)
        step += 1
    return "".join(out)


def encrypt(text, key):
    return _run(text, key, 1)


def decrypt(text, key):
    return _run(text, key, -1)


def heard(on_air, sent_mark, key):
    """Что видит слушатель с ключом key: (текст, свой ли ключ). on_air — текст как в эфире (шифровка или открытый)."""
    mine = mark(key) == (sent_mark or "")
    return (decrypt(on_air, key) if normalize(key) else on_air), mine
