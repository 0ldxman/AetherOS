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

# ---------- шаг 3: виджеты ----------

html = render("::stamp СЕКРЕТНО tone=green angle=-6")
check("виджет в одну строку",
      'class="stamp stamp--green"' in html and "СЕКРЕТНО" in html and "--angle: -6deg" in html)

html = render("::signature\nname: И. Иванов\nrole: Директор\n::")
check("виджет блоком: параметры из тела", "sig-name" in html and "Директор" in html)

html = render("::log\n02:14:07 INFO uplink\n::")
check("raw-виджет читает тело строками", "log-info" in html and "uplink" in html)

html = render("::stamp A\n\nтекст после")
check("однострочный виджет не съедает следующий текст", "<p>текст после</p>" in html)

html = render("::signature\nname: X\n\nтекст дальше")
check("незакрытый блок забирает только строку открытия",
      "текст дальше" in html and "sig-name" not in html)

html = render("::nosuch a=1")
check("неизвестный виджет: заглушка, не ошибка", "widget--unknown" in html and "::nosuch" in html)

html = render("::stamp <script>alert(1)</script>")
check("текст виджета экранируется", "<script>" not in html and "&lt;script&gt;" in html)

html = render("::stamp X tone=red;background:url(x) angle=abc")
check("мусор в tone и angle не попадает в атрибуты",
      "url(x)" not in html and "stamp--red" in html and "--angle: -8deg" in html)

html = render("::barcode hs-0047<script>")
check("штрихкод фильтруется", "<script>" not in html and "HS-0047SCRIPT" in html)

html = render("текст ::stamp X в середине строки")
check("виджет в середине строки это текст", "widget--stamp" not in html and "::stamp X" in html)

html = render("    ::stamp X\n    код")
check("виджет с отступом 4 пробела это код", "<pre>" in html and "widget--stamp" not in html)

# --- замазка внутри закрытого спойлера ---

html = render(spoiler("a", "::barcode SECRET-77"), keys=set())
check("закрытый спойлер: виджет без имени и данных",
      "SECRET-77" not in html and "barcode" not in html and "widget--masked" in html)

html = render(spoiler("a", "::stamp ТАЙНА tone=red"), keys=set())
check("закрытый спойлер: однострочный штамп", "ТАЙНА" not in html and "stamp" not in html.replace("widget--masked", ""))

html = render(spoiler("a", "::log\n02:14:07 INFO секрет-лог\n::"), keys=set())
check("закрытый спойлер: блочный log", "секрет-лог" not in html and "widget--masked" in html)

html = render(spoiler("a", "::stamp ТАЙНА"), keys={"a"})
check("открытый спойлер: виджет виден", "ТАЙНА" in html and "widget--stamp" in html)

# вложенность: блочный виджет внутри спойлера не должен закрыть спойлер раньше времени
html = render("::spoiler a\n::log\n02:14:07 INFO внутри\n::\nещё секрет\n::\n\nснаружи", keys=set())
check("блочный виджет в спойлере не рвёт вложенность",
      "внутри" not in html and "ещё" not in html and "снаружи" in html)

html = render("::spoiler a\n::stamp X\nещё секрет\n::\n\nснаружи", keys=set())
check("однострочный виджет в спойлере не закрывает спойлер",
      "секрет" not in html and "снаружи" in html)

nested = "::spoiler a\n::spoiler b\n::stamp ГЛУБОКО\n::\n::\n"
check("вложенные спойлеры: виджет виден только при обоих ключах",
      "ГЛУБОКО" in render(nested, keys={"a", "b"})
      and "ГЛУБОКО" not in render(nested, keys={"a"}))

# --- поиск ---

check("поиск: текст виджета не индексируется",
      "ТАЙНА" not in visible_text("::stamp ТАЙНА\n\nоткрытое", set()))

# ---------- шаг 4: контейнеры section и box ----------

html = render("::section 01 | REFERENCE: 99078-AA6\nТекст **раздела**.\n::")
check("section: номер, заголовок и тело",
      'class="section-num">01<' in html and "REFERENCE: 99078-AA6" in html
      and "<strong>раздела</strong>" in html and 'class="section-body"' in html)

html = render("::section Только заголовок\nтело\n::")
check("section без номера", "section-num" not in html and "Только заголовок" in html)

html = render("::section 01 | <b>x</b>\nтело\n::")
check("section: заголовок экранируется", "<b>" not in html and "&lt;b&gt;" in html)

html = render("::section\nтело\n::")
check("section без заголовка: нет шапки", "section-head" not in html and "тело" in html)

html = render("::box border center bigger url(x)\nтекст\n::")
check("box: только допустимые флаги",
      'class="box box--border box--center"' in html and "url(x)" not in html and "bigger" not in html)

html = render("::section 01 | Внешний\n::box border\nвнутри\n::\nещё\n::\n\nснаружи")
check("вложенность: box в section, текст после",
      "внутри" in html and "ещё" in html and "<p>снаружи</p>" in html
      and html.count("</div>") >= 5 and html.index("box--border") < html.index("внутри"))

html = render("::section A\n::stamp X\n::log\n02:14:07 INFO l\n::\nконец\n::\n\nснаружи")
check("виджеты внутри контейнера не рвут вложенность",
      "widget--stamp" in html and "log-info" in html and "конец" in html and "<p>снаружи</p>" in html)

html = render("::section A\nбез закрытия")
check("незакрытый section идёт до конца", "без закрытия" in html and "section-body" in html)

html = render("текст ::section A в середине")
check("section в середине строки это текст", "section-head" not in html and "::section A" in html)

html = render("    ::box border\n    код")
check("контейнер с отступом 4 пробела это код", "<pre>" in html and "box--border" not in html)

# --- замазка ---

html = render(spoiler("a", "::section 07 | СЕКРЕТНЫЙ ЗАГОЛОВОК\nсекретное тело\n::"), keys=set())
check("закрытый спойлер: заголовок и тело section не выводятся",
      "СЕКРЕТНЫЙ" not in html and "07" not in html and "секретное" not in html
      and "section--masked" in html)

html = render(spoiler("a", "::box dark center\nсекрет\n::"), keys=set())
check("закрытый спойлер: флаги box не выводятся",
      "box--dark" not in html and "box--center" not in html and "секрет" not in html)

html = render(spoiler("a", "::section 07 | ОТКРЫТЫЙ\nтело\n::"), keys={"a"})
check("открытый спойлер: section виден", "ОТКРЫТЫЙ" in html and "тело" in html)

html = render("::spoiler a\n::section 1 | Z\n::box\nглубоко\n::\n::\nещё секрет\n::\n\nснаружи", keys=set())
check("контейнеры в спойлере не рвут вложенность",
      "глубоко" not in html and "ещё" not in html and "<p>снаружи</p>" in html)

html = render("::section 1 | Z\n" + spoiler("a", "секрет") + "\n::", keys=set())
check("спойлер внутри section замазывается", "секрет" not in html and "spoiler--masked" in html)

# --- устойчивость ---

deep = "".join("::box\n" for _ in range(300)) + "дно\n" + "".join("::\n" for _ in range(300))
try:
    render(deep)
    check("глубокая вложенность не роняет рендер", True)
except RecursionError:
    check("глубокая вложенность не роняет рендер", False)

# ---------- шаг 5: сетка ----------

html = render("::grid cols=3\nа\n--\nб\n--\nв\n::")
check("grid: три ячейки, три колонки",
      html.count('class="cell"') == 3 and "repeat" not in html
      and html.count("minmax(0, 1fr)") == 3)

html = render("::grid cols=1,2,1\nа\n::")
check("grid: веса колонок", "minmax(0, 1fr) minmax(0, 2fr) minmax(0, 1fr)" in html)

for bad in ("cols=0", "cols=99", "cols=a", "cols=2,x", "cols=1;color:red", ""):
    html = render(f"::grid {bad}\nа\n::")
    check(f"grid: неверные cols ({bad!r}) дают 2 колонки, в стиль ничего лишнего",
          html.count("minmax(0, 1fr)") == 2 and "red" not in html)

html = render("::grid cols=4\nИванов\n--\nбез подписи\n-- label=\"AGENT NAME\"\nзначение\n::")
check("grid: label над содержимым",
      'class="cell-label">AGENT NAME<' in html and html.index("cell-label") < html.index("значение"))

html = render("::grid cols=4\nа\n-- span=2\nшироко\n-- span=9\nмного\n-- span=x\nмусор\n::")
check("grid: span, зажатый в границы колонок",
      'grid-column: span 2' in html and 'grid-column: span 4' in html
      and html.count("grid-column") == 2)

html = render("::grid cols=2\n-- label=\"A\"\nпервая\n--\nвторая\n::")
check("grid: ведущий -- не создаёт пустую ячейку",
      html.count('class="cell"') == 2 and 'cell-label">A<' in html and html.index("A<") < html.index("первая"))

html = render("::grid cols=3\nа\n--\n--\nв\n::")
check("grid: пустая ячейка между разделителями", html.count('class="cell"') == 3)

html = render("::grid cols=2\nИванов\n--\nтекст\n::")
check("grid: -- не превращает строку в заголовок", "<h2>" not in html and "Иванов" in html)

html = render("::grid cols=2\n| a | b |\n|---|---|\n| 1 | 2 |\n--\nпосле таблицы\n::")
check("grid: таблица и hr-подобные строки не делят ячейки",
      "<table>" in html and html.count('class="cell"') == 2)

html = render("::grid cols=2\n**жирный**\n--\n- один\n- два\n::")
check("grid: markdown внутри ячеек", "<strong>жирный</strong>" in html and "<li>один</li>" in html)

html = render("::grid cols=2\n::stamp X\n--\n::log\n02:14:07 INFO l\n::\n::")
check("grid: виджеты в ячейках, блочный log не рвёт разбор",
      "widget--stamp" in html and "log-info" in html and html.count('class="cell"') == 2)

html = render("::grid cols=2\nвнешняя 1\n--\n::grid cols=2\nвнутр 1\n--\nвнутр 2\n::\n--\nвнешняя 3\n::")
check("grid: вложенный grid со своими разделителями",
      html.count('<div class="grid"') == 2
      and html.count('class="cell"') == 5 and "внешняя 3" in html)

html = render("::section 1 | S\n::grid cols=2\nа\n--\nб\n::\nконец\n::\n\nснаружи")
check("grid внутри section, текст после", html.count('class="cell"') == 2 and "конец" in html and "<p>снаружи</p>" in html)

html = render("::grid cols=2\nбез закрытия\n--\nвторая")
check("незакрытый grid идёт до конца", html.count('class="cell"') == 2 and "вторая" in html)

html = render("текст ::grid cols=2 в середине")
check("grid в середине строки это текст", 'class="grid"' not in html and "::grid" in html)

many = "::grid cols=2\n" + "--\nх\n" * 500 + "::"
check("grid: лишние ячейки обрезаются", render(many).count('class="cell"') == 200)

# --- замазка ---

html = render(spoiler("a", "::grid cols=2\nсекрет 1\n-- label=\"СЕКРЕТНАЯ ПОДПИСЬ\" span=2\nсекрет 2\n::"), keys=set())
check("закрытый спойлер: grid без текста, подписей и раскладки",
      "секрет" not in html and "СЕКРЕТНАЯ" not in html and "grid-template" not in html
      and "grid-column" not in html and 'class="cell"' in html)

html = render(spoiler("a", "::grid cols=2\nоткрыто\n-- label=\"ПОДПИСЬ\"\nещё\n::"), keys={"a"})
check("открытый спойлер: grid виден", "открыто" in html and "ПОДПИСЬ" in html)

html = render("::spoiler a\n::grid cols=2\nх\n--\nу\n::\nещё секрет\n::\n\nснаружи", keys=set())
check("grid в спойлере не рвёт вложенность",
      "ещё" not in html and "<p>снаружи</p>" in html)

html = render("::grid cols=2\n" + spoiler("a", "секрет") + "\n--\nб\n::", keys=set())
check("спойлер внутри ячейки замазывается", "секрет" not in html and "spoiler--masked" in html)

html = render("::grid cols=2\n::spoiler a\nсекрет\n--\nещё секрет\n::\n--\nвидимое\n::", keys=set())
check("-- внутри спойлера внутри grid не делит ячейки",
      "секрет" not in html and html.count('class="cell"') == 2 and "видимое" in html)

# ---------- шаг 6: листы и ::page ----------

html = render("текст")
check("без ::page один лист без футера",
      html.count('class="sheet"') == 1 and "sheet-footer" not in html and "<p>текст</p>" in html)

html = render("первый\n::page HS-1 · стр. {n}/{total}\nвторой\n::page")
check("::page делит на листы, номера и total",
      html.count('class="sheet"') == 2 and "HS-1 · стр. 1/2" in html and "HS-1 · стр. 2/2" in html)

html = render("первый\n::page подпись {n}/{total}\n\nвторой")
check("последний лист без своего ::page берёт предыдущий футер",
      html.count('class="sheet"') == 2 and "подпись 2/2" in html)

html = render("первый\n::page A {n}\nвторой\n::page B {n}\nтретий")
check("у каждого листа свой футер",
      "A 1" in html and "B 2" in html and "B 3" in html and html.count("sheet-footer") == 3)

html = render("текст\n::page конец {n}/{total}")
check("::page в конце не создаёт пустой лист", html.count('class="sheet"') == 1 and "конец 1/1" in html)

html = render("::page только футер")
check("документ из одного ::page: один пустой лист с футером",
      html.count('class="sheet"') == 1 and "только футер" in html)

html = render("а\n::page\nб\n::section S\nвнутри\n::\nв")
check("пустой ::page не съедает следующие блоки",
      html.count('class="sheet"') == 2 and "внутри" in html and 'class="section"' in html)

html = render("а\n::section S\nб\n::page X\nв\n::\nг")
check("::page внутри контейнера игнорируется",
      html.count('class="sheet"') == 1 and "sheet-footer" not in html and "в" in html)

html = render(spoiler("a", "секрет\n::page Z\nещё"), keys=set())
check("::page в спойлере игнорируется, замазка цела",
      html.count('class="sheet"') == 1 and "Z" not in html and "секрет" not in html)

html = render("а\n::page X", variant="infobox")
check("в инфобоксе листов нет", "sheet" not in html and "<p>а</p>" in html)

html = render("а\n::page <b>X</b> {n}")
check("футер экранируется", "<b>" not in html and "&lt;b&gt;" in html)

html = render("а\n::page {n} {total} {x}")
check("только {n} и {total} подставляются", "1 1 {x}" in html)

html = render("а\n::page   \n")
check("пустой ::page: лист без футера", html.count('class="sheet"') == 1 and "sheet-footer" not in html)

check("поиск: ::page и футер не индексируются",
      "ФУТЕР" not in visible_text("текст\n::page ФУТЕР {n}", set()))