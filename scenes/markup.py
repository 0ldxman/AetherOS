"""Текст с разметкой для экранов, которые пишет автор (приветствие оболочки ОС): цвета тегами и подстановки в фигурных скобках.

    <dim>тусклый</dim>  <success>…</success>  <warning>…</warning>  <error>…</error>
    <rand>21-41</rand>   целое число из диапазона, при каждом показе своё (нагрузки)
    {host}              значение параметра; {{ и }} дают сами скобки; &lt; &gt; &amp; дают < > &

    <table> … </table>  колонки: в строках между тегами ячейки разделены |, ширина колонки считается по самой длинной
    <table gap=4>       ячейке (после подстановок), так что длинное имя хоста ничего не сдвигает; отступ строки сохраняется;
                        gap: пробелов между колонками (по умолчанию 3); сам знак | пишется &pipe;

Теги цвета открываются и закрываются в одной строке (в таблице: в одной ячейке), вкладываются (действует внутренний).
Пустая строка остаётся пустой.
Движок сцен (scenes.engine) шире, а здесь нарочно только это: для сцен будет свой, более богатый язык."""
import random
import re

from scenes.engine import STYLES, Scene

_TOKEN = re.compile(r"<(/?)(\w+)>|\{\{|\}\}|\{(\w*)\}|[{}<>]|&(?:lt|gt|amp|pipe);")
_RAND = re.compile(r"<rand>\s*(\d+)\s*-\s*(\d+)\s*</rand>")
_ENTITIES = {"&lt;": "<", "&gt;": ">", "&amp;": "&", "&pipe;": "|"}
_TABLE = re.compile(r"^\s*<table(?:\s+gap=(\d+))?>\s*$")
_END_TABLE = re.compile(r"^\s*</table>\s*$")
GAP = 3


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


def _table(rows, gap, params):
    """Строки таблицы (каждая: список ячеек-текстов шаблона) -> (строки из частей, ошибки [(индекс строки, текст)])."""
    cells, errors = [], []
    for index, row in enumerate(rows):
        parsed = []
        for number, text in enumerate(row):
            parts, found = parse_line(text.rstrip() if number == 0 else text.strip(), params)
            parsed.append(parts)
            errors += [(index, message) for message in found]
        cells.append(parsed)
    width = [0] * max((len(row) for row in cells), default=0)
    for row in cells:
        for number, parts in enumerate(row):
            width[number] = max(width[number], sum(len(text) for text, _ in parts))
    lines = []
    for row in cells:
        parts = []
        for number, cell in enumerate(row):
            parts += cell
            if number < len(row) - 1:
                shown = sum(len(text) for text, _ in cell)
                parts.append((" " * (width[number] - shown + gap), None))
        lines.append(parts)
    return lines, errors


def compile_lines(template, params):
    """Шаблон -> (строки [[(текст, стиль)]], ошибки [(номер строки шаблона с 1, текст)]). Таблицы выравниваются здесь."""
    lines, errors = [], []
    source = template.splitlines()
    index = 0
    while index < len(source):
        number, line = index + 1, source[index]
        opened = _TABLE.match(line)
        if opened:
            end = next((i for i in range(index + 1, len(source)) if _END_TABLE.match(source[i])), None)
            if end is None:
                errors.append((number, "Тег <table> не закрыт: нужен </table> на отдельной строке."))
                end = len(source)
            body = source[index + 1:end]
            rows, found = _table([row.split("|") for row in body], int(opened.group(1) or GAP), params)
            lines += rows
            errors += [(number + 1 + row, message) for row, message in found]
            index = end + 1
            continue
        if _END_TABLE.match(line):
            errors.append((number, "Тег </table> закрывает то, что не открыто."))
        else:
            parts, found = parse_line(line, params)
            lines.append(parts)
            errors += [(number, message) for message in found]
        index += 1
    return lines, errors


def check(template, names):
    """Ошибки шаблона: [(номер строки с 1, текст)]."""
    return compile_lines(template, dict.fromkeys(names))[1]


def render(template, params, scene=None):
    """Шаблон -> сцена. Ошибки не роняют вывод: неверное остаётся как есть (разбирает check при сохранении)."""
    scene = scene or Scene()
    for parts in compile_lines(template, params)[0]:
        scene.say(*parts) if parts else scene.blank()
    return scene
