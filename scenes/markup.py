"""Текст с разметкой для экранов, которые пишет автор (приветствие оболочки ОС): цвета тегами и подстановки в фигурных скобках.

    <dim>тусклый</dim>  <success>…</success>  <warning>…</warning>  <error>…</error>
    <rand>21-41</rand>   целое число из диапазона, при каждом показе своё (нагрузки)
    {host}              значение параметра; {{ и }} дают сами скобки; &lt; &gt; &amp; дают < > &

Теги открываются и закрываются в одной строке, вкладываются (действует внутренний). Пустая строка остаётся пустой.
Движок сцен (scenes.engine) шире, а здесь нарочно только это: для сцен будет свой, более богатый язык."""
import random
import re

from scenes.engine import STYLES, Scene

_TOKEN = re.compile(r"<(/?)(\w+)>|\{\{|\}\}|\{(\w*)\}|[{}<>]|&(?:lt|gt|amp);")
_RAND = re.compile(r"<rand>\s*(\d+)\s*-\s*(\d+)\s*</rand>")
_ENTITIES = {"&lt;": "<", "&gt;": ">", "&amp;": "&"}


def parse_line(line, params):
    """Строка -> (части [(текст, стиль)], ошибки [текст]). params: допустимые имена -> значения (или None, чтобы только проверить)."""
    parts, errors, stack, position = [], [], [], 0
    line = _RAND.sub(lambda m: str(random.randint(*sorted((int(m.group(1)), int(m.group(2)))))), line)

    def put(text):
        style = stack[-1] if stack else None
        if text and parts and parts[-1][1] == style:
            parts[-1] = (parts[-1][0] + text, style)
        elif text:
            parts.append((text, style))

    for token in _TOKEN.finditer(line):
        put(line[position:token.start()])
        position = token.end()
        text = token.group()
        closing, tag, name = token.groups()
        if tag:
            if tag == "rand":
                errors.append("Нужно <rand>от-до</rand>, например <rand>21-41</rand>.")
            elif tag not in STYLES:
                errors.append(f"Неизвестный тег <{tag}>; допустимы {', '.join(STYLES)}.")
            elif not closing:
                stack.append(tag)
            elif stack and stack[-1] == tag:
                stack.pop()
            else:
                errors.append(f"Тег </{tag}> закрывает не то, что открыто.")
        elif name is not None and text.startswith("{") and text != "{{":
            if name not in params:
                errors.append(f"Неизвестный параметр {{{name}}}.")
            else:
                put("" if params[name] is None else str(params[name]))
        elif text in ("{{", "}}"):
            put(text[0])
        elif text in _ENTITIES:
            put(_ENTITIES[text])
        else:
            errors.append(f"Одиночный {text!r}: для скобок пишите {{{{ }}}}, для < и > пишите &lt; &gt;.")
    put(line[position:])
    if stack:
        errors.append(f"Тег <{stack[-1]}> не закрыт до конца строки.")
    return parts, errors


def check(template, names):
    """Ошибки шаблона: [(номер строки с 1, текст)]."""
    found = []
    for number, line in enumerate(template.splitlines(), 1):
        found += [(number, text) for text in parse_line(line, dict.fromkeys(names))[1]]
    return found


def render(template, params, scene=None):
    """Шаблон -> сцена. Ошибки не роняют вывод: неверное остаётся как есть (разбирает check при сохранении)."""
    scene = scene or Scene()
    for line in template.splitlines():
        parts = parse_line(line, params)[0]
        scene.say(*parts) if parts else scene.blank()
    return scene
