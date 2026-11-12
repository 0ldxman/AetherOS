"""Письмо как текст: заголовки (From, To, Subject, Date, свои X-…), пустая строка и тело.

Так письмо лежит в файле объекта формата msg и так его видит игрок в «оригинале письма». Подстановки {player}, {login},
{to}, {date} заменяются, когда игрок открывает письмо: одно письмо автора обращается к каждому игроку по-своему.
"""
import re
from dataclasses import dataclass, field

HEADER = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):[ \t]?(.*)$")
PLACEHOLDER = re.compile(r"\{(player|login|to|date|address|world_\w+)\}")     # world_<счётчик>: значение счётчика мира


@dataclass
class Letter:
    headers: list = field(default_factory=list)      # [(имя, значение)] в порядке письма
    body: str = ""

    def get(self, name, default=""):
        name = name.lower()
        for key, value in self.headers:
            if key.lower() == name:
                return value
        return default

    @property
    def sender(self):
        return self.get("From")

    @property
    def to(self):
        return self.get("To")

    @property
    def subject(self):
        return self.get("Subject")


def parse(text):
    """Письмо из текста. Без строк «Имя: значение» в начале весь текст считается телом."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    headers, at = [], 0
    while at < len(lines):
        line = lines[at]
        if not line.strip():
            at += 1
            break
        found = HEADER.match(line)
        if found:
            headers.append((found.group(1), found.group(2).strip()))
        elif headers and line[:1] in (" ", "\t"):
            name, value = headers[-1]
            headers[-1] = (name, f"{value} {line.strip()}")              # продолжение заголовка на новой строке
        else:
            return Letter([], text)
        at += 1
    if not headers:
        return Letter([], text)
    return Letter(headers, "\n".join(lines[at:]))


def compose(headers, body):
    """Текст письма из заголовков и тела."""
    head = "\n".join(f"{name}: {value}" for name, value in headers if value is not None)
    return f"{head}\n\n{body}" if head else body


def fill(text, context):
    """Подстановки игрока в тексте письма; неизвестные остаются как есть."""
    def value(found):
        name = found.group(1)
        if name.startswith("world_") and name not in context:
            from world.state import params

            return str(params().get(name, found.group(0)))
        return str(context.get(name, found.group(0)))

    return PLACEHOLDER.sub(value, text or "")
