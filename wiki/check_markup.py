"""Проверка markup.py. Запуск из корня проекта: python -m wiki.check_markup"""

from wiki.markup import (
    MASK_CHAR, SpoilerSyntaxError, parse_expr, render, visible_text,
)


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)


def spoiler(expr, body="Секретный текст"):
    return f"до\n\n::spoiler {expr}\n{body}\n::\n\nпосле"


# ---------- шаг 1: обычный markdown ----------

html = render("# Заголовок\n\nТекст с **жирным** и ~~зачёркнутым~~.")
check("заголовок", "<h1>Заголовок</h1>" in html)
check("жирный", "<strong>жирным</strong>" in html)
check("зачёркнутый", "<s>зачёркнутым</s>" in html)

html = render("| a | b |\n|---|---|\n| 1 | 2 |")
check("таблица", "<table>" in html and "<td>1</td>" in html)

html = render("<script>alert(1)</script>")
check("сырой html экранируется", "<script>" not in html and "&lt;script&gt;" in html)

html = render("[клик](javascript:alert(1))")
check("javascript: не становится ссылкой", "<a " not in html)

html = render("[ок](https://example.com)")
check("обычная ссылка работает", '<a href="https://example.com">ок</a>' in html)

check("пустой текст", render("") == '<div class="md md--body"></div>')
check("None как пустой", render(None) == '<div class="md md--body"></div>')
check("вариант infobox", 'class="md md--infobox"' in render("x", variant="infobox"))

try:
    render("x", variant="нет")
    check("неизвестный вариант: ошибка", False)
except ValueError:
    check("неизвестный вариант: ошибка", True)

# ---------- шаг 2: условия ----------

check("условие: один ключ", parse_expr("a") == "a")
check("условие: and", parse_expr("a and b") == {"all": ["a", "b"]})
check("условие: or", parse_expr("a or b") == {"any": ["a", "b"]})
check("условие: not", parse_expr("not a") == {"not": "a"})
check("условие: and сильнее or",
      parse_expr("a or b and c") == {"any": ["a", {"all": ["b", "c"]}]})
check("условие: скобки",
      parse_expr("(a or b) and c") == {"all": [{"any": ["a", "b"]}, "c"]})
check("условие: слитные скобки", parse_expr("(a)and(b)") == {"all": ["a", "b"]})

for bad in ["", "   ", "a and", "and a", "(a", "a)", "a b", "not", "a or or b", "a$b", "x" * 300]:
    try:
        parse_expr(bad)
        check(f"условие {bad[:12]!r}: ошибка", False)
    except SpoilerSyntaxError:
        check(f"условие {bad[:12]!r}: ошибка", True)

# ---------- шаг 2: открытый спойлер ----------

html = render(spoiler("key_a", "Секрет **жирный**"), keys={"key_a"})
check("открытый: текст виден", "Секрет <strong>жирный</strong>" in html)
check("открытый: класс", 'class="spoiler spoiler--open"' in html)
check("открытый: ключ не в html", "key_a" not in html)
check("открытый: текст вокруг на месте", "<p>до</p>" in html and "<p>после</p>" in html)

# ---------- шаг 2: закрытый спойлер ----------

html = render(spoiler("key_a", "Секрет два слова"), keys=set())
check("закрытый: текста нет", "Секрет" not in html and "слова" not in html)
check("закрытый: замазка по символам",
      f"{MASK_CHAR * 6} {MASK_CHAR * 3} {MASK_CHAR * 5}" in html)
check("закрытый: класс и aria", 'class="spoiler spoiler--masked"' in html and 'aria-hidden="true"' in html)
check("закрытый: ключ не в html", "key_a" not in html)
check("закрытый: текст вокруг на месте", "<p>до</p>" in html and "<p>после</p>" in html)

html = render(spoiler("k", "[тайная](https://secret.example/x) ссылка"), keys=set())
check("закрытый: адрес ссылки вырезан", "secret.example" not in html and "<a " not in html)

html = render(spoiler("k", "![подпись](https://secret.example/i.png)"), keys=set())
check("закрытый: картинка вырезана", "secret.example" not in html and "<img" not in html and "подпись" not in html)

html = render(spoiler("k", "```python\nprint('пароль')\n```"), keys=set())
check("закрытый: код и язык вырезаны", "пароль" not in html and "python" not in html and "print" not in html)

html = render(spoiler("k", "`инлайн код`"), keys=set())
check("закрытый: инлайн-код замазан", "инлайн" not in html)

html = render(spoiler("k", "- пункт один\n- пункт два"), keys=set())
check("закрытый: структура списка есть, текста нет", "<li>" in html and "пункт" not in html)

html = render(spoiler("k", "| секрет | да |\n|---|---|\n| тайна | нет |"), keys=set())
check("закрытый: таблица замазана", "<table>" in html and "секрет" not in html and "тайна" not in html)

# ---------- шаг 2: выражения в деле ----------

check("and: один ключ из двух закрыт",
      "Секрет" not in render(spoiler("a and b"), keys={"a"}))
check("and: оба ключа открывают",
      "Секрет" in render(spoiler("a and b"), keys={"a", "b"}))
check("or: хватает одного",
      "Секрет" in render(spoiler("a or b"), keys={"b"}))
check("not: открыт без ключа",
      "Секрет" in render(spoiler("not a"), keys=set()))
check("not: закрыт с ключом",
      "Секрет" not in render(spoiler("not a"), keys={"a"}))

# ---------- шаг 2: закрыто при ошибках ----------

for bad in ["", "a and", "(a", "a b"]:
    html = render(spoiler(bad), keys={"a", "b"})
    check(f"неверное условие {bad!r}: закрыто", "Секрет" not in html and "spoiler--masked" in html)

html = render("::spoiler\nСекрет\n::")
check("без условия: закрыто", "Секрет" not in html)

html = render("до\n\n::spoiler a\nСекрет без конца", keys={"b"})
check("незакрытый блок: замазан до конца", "Секрет" not in html)

html = render("до\n\n::spoiler a\nСекрет без конца", keys={"a"})
check("незакрытый блок: открывается ключом", "Секрет" in html)

# ---------- шаг 2: вложенность ----------

nested = "::spoiler a\nвнешний\n\n::spoiler b\nвнутренний\n::\n\nещё внешний\n::"
html = render(nested, keys={"a", "b"})
check("вложенные: оба открыты", "внешний" in html and "внутренний" in html)

html = render(nested, keys={"a"})
check("вложенные: внутренний закрыт, внешний виден",
      "внутренний" not in html and "ещё внешний" in html)

html = render(nested, keys={"b"})
check("вложенные: внешний закрыт, внутренний тоже",
      "внешний" not in html and "внутренний" not in html)

# ---------- шаг 2: границы синтаксиса ----------

html = render("текст ::spoiler a в середине строки")
check("в середине строки это просто текст", "::spoiler a" in html and "spoiler--" not in html)

html = render("    ::spoiler a\n    код")
check("с отступом 4 пробела это код", "<pre>" in html and "spoiler--" not in html)

html = render("абзац\n::spoiler a\nсекрет\n::", keys=set())
check("спойлер сразу после абзаца", "спойлер" not in html and "секрет" not in html and "spoiler--masked" in html)

html = render("::spoilerx a\nтекст\n::")
check("::spoilerx не спойлер", "spoiler--" not in html)

html = render(spoiler("a", "- один\n- два"), keys={"a"})
check("открытый: список внутри", "<li>один</li>" in html)

# ---------- шаг 2: текст для поиска ----------

text = spoiler("a", "Секрет") + "\n\nпубличное **слово**"
check("поиск: закрытое вырезано", "Секрет" not in visible_text(text, set()))
check("поиск: открытое есть", "Секрет" in visible_text(text, {"a"}))
check("поиск: открытый текст без разметки", "публичное слово" in visible_text(text, set()))
check("поиск: ссылка в закрытом не находится",
      "secret.example" not in visible_text(spoiler("a", "[т](https://secret.example)"), set()))
check("поиск: код открытого находится",
      "пароль" in visible_text(spoiler("a", "```\nпароль\n```"), {"a"}))