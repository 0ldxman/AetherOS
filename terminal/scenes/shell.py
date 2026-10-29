"""Сцены терминала: анимация вокруг ответа команды и приветствие оболочки.

Это тот же язык, что у загрузки и входа (scenes/engine.py). Сцена только показывает работу команды;
решение (слой снят или нет) принимает сервер раньше и кладёт его в сцену как готовый результат. Текст ответа
остаётся обычным и печатается после сцены. В сцену, как и в ответ, попадает только то, что игрок уже вправе видеть.
"""
import hashlib

from scenes.engine import Scene
from scenes import markup
from scenes.gateway import GAME_DATE, _motd


def _stable(seed, low, high):
    """Число от low до high, у одного seed всегда одно и то же (размер «файла» не прыгает между запусками)."""
    value = int.from_bytes(hashlib.sha256(str(seed).encode()).digest()[:4], "big")
    return low + value % (high - low + 1)


def _result(ok):
    return "OK" if ok else "FAIL"


# ---------- снятие слоёв ----------

def _encrypted(s, path, ok):
    s.task("reading header", "OK", ms=(180, 380))
    s.bar("deriving key ", ms=(700, 1300), width=20)
    s.task("checking passphrase", _result(ok), ms=(350, 800))


def _binary(s, path, ok):
    s.count("scanning", _stable(path, 400, 9000), unit=" bytes", ms=(500, 1000), width=10)
    s.task("collecting strings", _result(ok), ms=(300, 700))


def _shifted(s, path, ok):
    s.task("seeking", "OK", ms=(200, 450))
    s.bar("reading ", ms=(500, 1000), width=20)
    s.task("block check", _result(ok), ms=(250, 550))


def _disguised(s, path, ok):
    s.task("probing format", "OK", ms=(250, 500))
    s.bar("converting ", ms=(600, 1200), width=20)
    s.task("validating", _result(ok), ms=(250, 600))


def _generic(s, path, ok):
    s.task("working", _result(ok), ms=(300, 800))


_UNLOCK = {"encrypted": _encrypted,
           "binary": _binary, "shifted": _shifted, "disguised": _disguised}


def unlock_scene(layer, path, ok):
    """Работа команды, снимающей слой файла: ok это уже принятое сервером решение."""
    scene = Scene()
    _UNLOCK.get(layer, _generic)(scene, path, ok)
    return scene.to_dict()


def repair_scene(path, size, ok, more):
    """Восстановление файла (rpr): проходы как у fsck и ddrescue, а восстановление блоков идёт сразу по всем плохим,
    каждый со своим темпом. more значит, что под снятым слоем лежит ещё один damaged: часть блоков за этот проход не
    поддаётся (их полоса встаёт и кончается FAIL). Сервер уже решил исход (ok, more)."""
    blocks = max(8, -(-size // 512))
    bad = min(blocks - 1, _stable(path, 3, 9))
    lost = _stable(path + ":rest", 1, max(1, bad // 2)) if more else 0

    numbers, index = [], 0
    while len(numbers) < bad:
        number = _stable(f"{path}:{index}", 0, blocks - 1)
        index += 1
        if number not in numbers:
            numbers.append(number)
    numbers.sort()

    order = sorted(range(bad), key=lambda i: _stable(f"{path}:o{i}", 0, 10**6))
    failing = set(order[:lost])
    rows = []
    for i, number in enumerate(numbers):
        start = 900 + _stable(f"{path}:t{i}", 0, 1800)          # у каждого блока свой темп
        row = (f"  block {number:05d} ", (start, start + 600))
        rows.append(row + (("FAIL", 35 + _stable(f"{path}:s{i}", 0, 50)) if i in failing else ()))

    s = Scene()
    s.row("rpr", path, width=8)
    s.row("size", f"{size} bytes", note=f"{blocks} blocks of 512", width=8)
    s.blank()
    s.count("pass 1/4  surface scan", blocks, unit=" blk", ms=(min(2600, 500 + blocks * 9), min(3200, 800 + blocks * 12)), width=26)
    s.say(f"  {bad} damaged blocks", style="warning")
    s.task("pass 2/4  rebuilding block map", "OK", ms=(500, 1000))
    s.say("pass 3/4  reconstructing from parity")
    s.bars(rows, width=14)
    s.say(f"  recovered {bad - lost} of {bad} blocks", style="warning" if lost else "dim")
    s.task("pass 4/4  verifying checksums", "FAIL" if not ok else ("WARN" if more else "OK"), ms=(400, 800))
    return s.to_dict()           # вердикт (repaired, further repair required) говорит ответ команды


# ---------- архивы ----------

def pak_list_scene(path, count):
    """pak l: чтение заголовка и таблицы архива."""
    s = Scene()
    s.task("reading header", "OK", ms=(150, 350))
    s.count("reading index", max(1, count), unit=" entries", ms=(250 + 60 * min(count, 12), 450 + 90 * min(count, 12)), width=16)
    return s.to_dict()


def pak_extract_scene(path, names, ok=True):
    """pak x: каждый файл своей полосой (до восьми, остальные одной строкой)."""
    s = Scene()
    s.task("reading header", "OK", ms=(150, 350))
    s.say(f"extracting {len(names)} file{'s' if len(names) != 1 else ''}")
    shown = names[:8]
    width = max([6] + [len(name.rsplit("/", 1)[-1]) for name in shown])
    rows = []
    for i, name in enumerate(shown):
        start = 300 + _stable(f"{path}:{name}:t", 0, 1100)
        rows.append((f"  {name.rsplit('/', 1)[-1]:<{width}} ", (start, start + 450)))
    if rows:
        s.bars(rows, width=14)
    if len(names) > len(shown):
        s.say(f"  ... {len(names) - len(shown)} more")
    s.task("verifying", "OK" if ok else "FAIL", ms=(200, 450))
    return s.to_dict()


# ---------- расшифровка ключом ----------

def key_scene(path, ok):
    """ward -k: заголовок пакета, секретный ключ, сессионный ключ."""
    s = Scene()
    s.task("reading packet header", "OK", ms=(150, 350))
    s.task("loading secret key", "OK", ms=(200, 450))
    s.bar("decrypting session key ", ms=(600, 1200), width=14)
    s.task("checking session key", "OK" if ok else "FAIL", ms=(300, 700))
    return s.to_dict()


# ---------- подписи ----------

def verify_scene(path, count, ok):
    """ward verify: чтение блоков подписи, хеш содержимого и сверка."""
    s = Scene()
    s.task("reading signature", "OK" if count else "FAIL", ms=(150, 350))
    if count:
        s.bar("hashing content ", ms=(500, 1000), width=14)
        s.task("checking signature", "OK" if ok else "FAIL", ms=(300, 700))
    return s.to_dict()


def sign_scene(path, key):
    """ward sign: хеш файла и подпись секретным ключом."""
    s = Scene()
    s.task("loading secret key", "OK", ms=(200, 450))
    s.bar("hashing content ", ms=(500, 1000), width=14)
    s.task("signing", "OK", ms=(350, 800))
    s.task("writing signature", "OK", ms=(150, 350))
    return s.to_dict()


# ---------- сырые байты ----------

def block_scene(path, out, start, end, scanning, size, errors=()):
    """blk: чтение окна и запись нового файла. scanning: конец окна не назван, и команда ищет конец файла; после поиска
    показывает его адрес. errors это блоки с ошибкой чтения (damaged). Решение, настоящий ли файл получится, сцене не
    известно: она одинакова для верного и неверного окна."""
    blocks = max(1, -(-(end - start) // 512))
    s = Scene()
    s.row("blk", path, width=8)
    s.row("output", out, width=8)
    s.row("window", f"0x{start:x} - " + ("EOF" if scanning else f"0x{end:x}"), width=8)
    s.blank()
    s.task("seeking", "OK", ms=(60, 160))
    if scanning:
        total = max(1, -(-(size - start) // 512))
        s.count("scanning for EOF", total, unit=" blk", ms=(min(2200, 400 + total * 9), min(2800, 700 + total * 12)), width=22)
        s.say(f"  EOF at 0x{size:x}")
    s.task(f"reading {blocks} block{'s' if blocks != 1 else ''}", "WARN" if errors else "OK", ms=(60 * blocks, 110 * blocks))
    for number in list(errors)[:3]:
        s.say(f"  I/O error at block {number}", style="warning")
    s.task("writing output", "OK", ms=(150, 400))
    return s.to_dict()


def strings_scene(path, size):
    """txtx: просмотр байтов в поисках читаемого."""
    s = Scene()
    s.count("scanning", size, unit=" B", ms=(150, 450), width=10)
    return s.to_dict()


# что читает cvt у формата: названия единиц разбора (формат -> (крупные, мелкие)); для незнакомого берутся общие
FORMAT_UNITS = {
    "pdf": ("pages", "objects"), "png": ("chunks", "scanlines"), "jpg": ("segments", "tables"), "gif": ("frames", "colors"),
    "zip": ("entries", "headers"), "gz": ("members", "blocks"), "wav": ("channels", "frames"), "mp3": ("frames", "tags"),
    "rec": ("fields", "lines"), "snp": ("nodes", "styles"), "msg": ("headers", "lines"), "pak": ("entries", "blocks"),
    "app": ("sections", "symbols"),
    "bmp": ("rows", "pixels"), "tiff": ("directories", "tags"), "webp": ("chunks", "frames"), "ico": ("images", "entries"),
    "psd": ("layers", "channels"), "ogg": ("pages", "packets"), "flac": ("blocks", "frames"), "mid": ("tracks", "events"),
    "mp4": ("boxes", "samples"), "mkv": ("elements", "clusters"), "avi": ("streams", "chunks"), "7z": ("entries", "folders"),
    "rar": ("entries", "blocks"), "bz2": ("blocks", "symbols"), "xz": ("blocks", "records"), "exe": ("sections", "imports"),
    "dll": ("sections", "exports"), "elf": ("segments", "symbols"), "class": ("methods", "constants"),
    "sqlite": ("pages", "tables"), "pcap": ("packets", "flows"), "kdbx": ("groups", "entries"), "rtf": ("groups", "controls"),
    "html": ("nodes", "styles"), "xml": ("elements", "attributes"), "json": ("keys", "values"), "csv": ("rows", "columns"),
    "txt": ("lines", "words"), "md": ("blocks", "lines"), "log": ("entries", "lines"), "svg": ("nodes", "paths"),
    "eml": ("headers", "parts"), "pem": ("blocks", "lines"), "pgp": ("packets", "lines"), "ssh": ("blocks", "lines"),
    "sh": ("commands", "lines"), "py": ("statements", "lines"), "map": ("layers", "features"),
}
# кодировка слоя binary (вид из реестра) -> (единицы, что проверяется перед разбором)
ENCODING_STEPS = {
    "codec": ("code units", "checking byte order"), "hex": ("octets", "checking digit pairs"),
    "rot": ("letters", "mapping alphabet"), "xor": ("bytes", "applying key stream"),
    "gzip": ("blocks", "inflating deflate stream"), "morse": ("symbols", "splitting dots and dashes"),
    "reverse": ("bytes", "reversing order"), "base32": ("quanta", "checking padding"),
    "rot47": ("symbols", "mapping printable range"), "bin": ("bits", "grouping bytes"),
    "dec": ("numbers", "parsing decimal codes"), "oct": ("numbers", "parsing octal codes"),
    "url": ("escapes", "checking percent escapes"), "base85": ("groups", "checking alphabet"),
    "uu": ("lines", "checking line lengths"), "atbash": ("letters", "mapping reversed alphabet"),
    "base64": ("characters", "checking alphabet and padding"),
}


def _decode_rows(path, names):
    """Части формата читаются сразу все, каждая в своём темпе."""
    rows = []
    width = max([6] + [len(name.strip()) for name in names])
    for i, name in enumerate(names):
        start = 500 + _stable(f"{path}:p{i}", 0, 1400)
        rows.append((f"  {name.strip():<{width}} ", (start, start + 500)))
    return rows


def extract_scene(path, offset, found, known):
    """kex: чтение блока по смещению и разбор его шапки. found: на этом месте блок ключа, known: такой ключ существует.
    Сервер уже решил исход; сцена до разбора шапки ничего не выдаёт."""
    s = Scene()
    s.row("kex", path, width=8)
    s.row("offset", f"0x{offset:x}", width=8)
    s.blank()
    s.task("seeking", "OK", ms=(80, 200))
    s.task("reading block", "OK", ms=(150, 400))
    s.task("parsing armor", "OK" if found else "FAIL", ms=(300, 800))
    if not found:
        return s.to_dict()
    s.task("checking keyname", "OK" if known else "FAIL", ms=(300, 700))
    if known:
        s.task("writing key", "OK", ms=(200, 500))
    return s.to_dict()


def convert_scene(path, size, value, ok, out):
    """cvt ext: чтение файла как названного формата и запись результата. out это куда ляжет копия (None: тот же файл,
    расширение заменяется). Решение уже принято сервером: неверное название обрывается на разборе входа, и по сцене
    ничего не узнать раньше ответа. Единицы разбора берутся из формата: у записи поля, у страницы узлы, у документа и
    скана их части (каждая своей полосой)."""
    from filesystem.content.rawview import registry

    s = Scene()
    s.row("cvt", path, width=8)
    s.row("size", f"{size} bytes", width=8)
    s.row("format", f"{value}", note="read as requested", width=8)
    s.row("output", out or path, note="" if out else "in place", width=8)
    s.blank()
    s.task("probing input", "OK" if ok else "FAIL", ms=(500, 1100))
    if not ok:
        return s.to_dict()

    fmt = registry.format_named(value.lower())
    names = [part.name for part in fmt.parts] if fmt else []
    if fmt and fmt.kind in ("chunks", "package", "zip"):
        what = {"chunks": "chunks", "package": "parts", "zip": "entries"}[fmt.kind]
        s.task({"chunks": "reading chunk table", "package": "reading part table", "zip": "reading central directory"}[fmt.kind],
               "OK", ms=(200, 500))
        shown = [name.rsplit("/", 1)[-1] for name in names]
        s.row(f"  {what}", f"{len(names)}  ({', '.join(name.strip() for name in shown)})", width=16)
        s.say(f"decoding {what}")
        s.bars(_decode_rows(path, shown), width=14)
    else:
        big, small = FORMAT_UNITS.get(fmt.name if fmt else value.lower(), ("blocks", "records"))
        s.row("  " + big, str(max(1, min(size // 48, _stable(path + ":a", 1, 40)))), width=16)
        s.row("  " + small, str(max(2, min(size // 8, _stable(path + ":b", 60, 900)))), width=16)
        s.bar("decoding streams ", ms=(900, 1800), width=14)
    s.task("writing output", "OK", ms=(300, 700))
    return s.to_dict()


def decode_scene(path, size, value, ok):
    """cvt enc: раскодирование слоя binary из названной кодировки. Решение уже принято сервером: неверная кодировка
    обрывается на проверке потока, и по сцене ничего не узнать раньше ответа. Шаги и единицы зависят от вида кодировки."""
    from filesystem.content.rawview import registry

    found = registry.encoding_named(value.lower())
    unit, check = ENCODING_STEPS.get(found.kind if found else "", ("units", "checking stream"))
    if found and found.kind == "codec":
        codec = found.param.lower()
        if codec.startswith(("utf-16", "utf-32")):
            pass                                                    # единицы и порядок байтов
        elif codec == "utf-7":
            unit, check = "code units", "checking shift sequences"
        else:
            unit, check = "bytes", "checking code page"
    s = Scene()
    s.row("cvt", path, width=9)
    s.row("size", f"{size} bytes", width=9)
    s.row("encoding", value, note="decode as requested", width=9)
    s.blank()
    s.task("probing stream", "OK", ms=(300, 700))
    s.task(check, "OK" if ok else "FAIL", ms=(400, 900))
    if not ok:
        return s.to_dict()
    s.row("  " + unit, str(max(1, size)), width=16)
    s.bar("decoding stream ", ms=(900, 1800), width=14)
    s.task("verifying text", "OK", ms=(200, 500))
    s.task("writing output", "OK", ms=(300, 700))
    return s.to_dict()


# ---------- просмотр файла ----------

def ftyp_scene(path):
    """Определение типа смотрит только заголовок и потому быстрое. Одинаковая для любого файла: по ней ничего не узнать
    раньше ответа."""
    s = Scene()
    s.task("reading header", "OK", ms=(60, 160))
    return s.to_dict()


def open_scene(path, stage):
    """Открытие содержимого. stage говорит, где оно остановилось (решение принято сервером раньше): access (доступ
    закрыт слоем), content (открывать нечего), opened (окно открылось). Читать данных тут нет: окно читает их само."""
    s = Scene()
    s.task("checking access", "FAIL" if stage == "access" else "OK", ms=(120, 300))
    if stage != "access":
        s.task("locating content", "FAIL" if stage == "content" else "OK", ms=(120, 280))
    if stage == "opened":
        s.task("launching viewer", "OK", ms=(200, 450))
    return s.to_dict()


# ---------- корзина ----------

def trash_scene(count):
    s = Scene()
    s.task("moving to trash", "OK", ms=(150, 400))
    return s.to_dict()


def recover_scene(path):
    s = Scene()
    s.count("scanning trash", _stable(path, 120, 1800), unit=" blocks", ms=(500, 1000), width=10)
    s.bar("recovering ", ms=(700, 1400), width=20)
    s.task("checksum", "WARN", ms=(250, 550))
    return s.to_dict()


def wipe_scene(count):
    s = Scene()
    s.bar("overwriting ", ms=(500, 1100), width=20)
    s.task("trash emptied", "OK", ms=(150, 350))
    return s.to_dict()


# ---------- приветствие ----------

# что можно подставить в приветствие ОС: имя -> подпись для студии
GREETING_PARAMS = {
    "host": "имя машины", "login": "логин учётки", "os": "код ОС", "os_name": "название ОС", "address": "адрес узла (частота или сетевой)", "serial": "серийный номер",
    "hid": "hid машины", "host_key": "отпечаток ключа узла", "freq": "частота учётки, под которой вошли", "date": "дата в мире", "last_login": "прошлый вход этой учётки",
    "uptime": "сколько работает машина", "accounts": "число учёток машины", "sessions": "сколько игроков на машине сейчас",
    "unread": "число непрочитанных писем", "mail": "строка про непрочитанную почту", "volumes": "тома машины", "note": "заметка машины",
}


def _mail_text(mail):
    unread = (mail or {}).get("unread", 0)
    if not unread:
        return "no new messages"
    latest = f"latest from {mail['sender']}, {mail['ago']} ago" if mail["sender"] else f"latest {mail['ago']} ago"
    return f"{unread} unread {'message' if unread == 1 else 'messages'} ({latest})"


def greeting_params(ident, login, mail=None, system=None, facts=None):
    """Значения для приветствия. facts: то, что берётся из базы (machines.world.facts); без него остаются условные."""
    facts = {"accounts": 0, "sessions": 0, "last_login": "never", "uptime": "unknown", "note": "", "volumes": "none", "freq": None, **(facts or {})}
    return {
        "host": ident.hostname, "login": login, "os": system.code if system else "", "os_name": system.name if system else "",
        "address": ident.address, "serial": ident.serial, "hid": ident.hid, "host_key": ident.host_key, "date": GAME_DATE,
        "unread": (mail or {}).get("unread", 0), "mail": _mail_text(mail), **{**facts, "freq": facts["freq"] or ident.address},
    }


def greeting_scene(ident, login, mail=None, system=None, facts=None):
    """Оболочка открылась. Если у ОС задано своё приветствие (SystemType.greeting), показывается оно, иначе общее ниже."""
    if system is not None and system.greeting.strip():
        return markup.render(system.greeting, greeting_params(ident, login, mail, system, facts)).to_dict()
    return _default_greeting(ident, login, mail)


def _default_greeting(ident, login, mail=None):
    """Оболочка открылась: шапка сеанса, то же приветствие узла, что после входа (логотип, нагрузка, радио,
    уведомления, последний вход, почта) и подсказка. Каждое окно терминала начинается так; любая клавиша доигрывает."""
    s = Scene()
    s.say(f"aether-shell 1.4 on {ident.hostname}", style="dim")
    s.task("pty       allocating 120x32 ", "OK", ms=(150, 320))
    s.task("env       TERM=aether-256 ", "OK", ms=(120, 260))
    s.task(f"session   {login} ", "OK", ms=(180, 360))
    s.say("recording on", style="dim")
    _motd(s, ident, login, mail, read=False)
    s.say("  Type ", ("ls", "success"), " to look around, ", ("clear", "success"), " to wipe the screen.", style="dim")
    s.blank()
    return s.to_dict()
