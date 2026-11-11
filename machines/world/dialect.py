"""Диалект путей: как машина показывает и принимает пути. Внутри пути канонические (``/home/ivan``, ``/C:/Users/ivan``).

Шаблоны мест (``{home}/.secrets``) тоже приводятся к каноническому виду, но подстановки остаются как есть: путь из них
собирается и проверяется уже после подстановки (machines.world.places).
"""
import re

UNIX = "unix"
WINDOWS = "windows"
VMS = "vms"          # DSK0:[OPS.IVAN.DESK]CONSOLE.APP;1
MVS = "mvs"          # OPS.IVAN.DESK.CONSOLE, 'SYS1.PARMLIB(IEASYS00)'
MULTICS = "multics"  # >udd>Ops>Ivan>note, < это вверх
CPM = "cpm"          # A3:NOTE.TXT: диск и область пользователя, папок нет
PRIMOS = "primos"    # <DISK0>OPS>IVAN>NOTE, * это текущая папка
MAC = "mac"          # Macintosh HD:System Folder:Finder, :Desk: от текущей, :: это вверх
CASELESS = {WINDOWS, VMS, MVS, CPM, PRIMOS, MAC}       # регистр в имени не важен: ввод сверяется с файлами без учёта регистра (терминал)


class PathSyntax(ValueError):
    """Путь не разбирается в диалекте машины: текст для игрока (по-английски, как весь терминал)."""

_DRIVE_START = re.compile(r"^[A-Za-z]:(?=[\\/]|$)")


def to_canonical(path):
    """Путь или шаблон, как его ввели (``C:\\Users\\{login}`` или ``/home/{login}``), -> канонический (``/C:/Users/{login}``)."""
    text = (path or "").strip().replace("\\", "/")
    if not text:
        return ""
    if _DRIVE_START.match(text):
        text = "/" + text[0].upper() + text[1:]
    parts = [part for part in text.split("/") if part]
    prefix = "/" if text.startswith("/") else ""
    return prefix + "/".join(parts)


def to_display(path, style, is_dir=True):
    """Канонический путь -> вид в диалекте системы: ``/C:/Users/ivan`` -> ``C:\\Users\\ivan``.

    is_dir важен для VMS (папка ``[OPS.IVAN]``, файл ``[OPS]IVAN.TXT;1``) и мейнфрейма (корень каталога ``*``)."""
    if not path:
        return path
    if style == WINDOWS:
        return _windows_show(path)
    if style == VMS:
        return _vms_show(path, is_dir)
    if style == MVS:
        return _mvs_show(path)
    if style == MULTICS:
        return _multics_show(path)
    if style == CPM:
        return _cpm_show(path)
    if style == PRIMOS:
        return _primos_show(path)
    if style == MAC:
        return _mac_show(path, is_dir)
    return path


def parse(text, style, cwd="/"):
    """Путь, как его ввели в диалекте машины (абсолютный или относительный к cwd), -> канонический абсолютный.

    Путь со слэшем в начале понимается всеми диалектами как канонический. Ошибку синтаксиса сообщает PathSyntax."""
    text = (text or "").strip()
    if not text:
        return cwd
    if style == WINDOWS:
        return _windows_parse(text, cwd)
    if style == VMS and not text.startswith("/"):
        return _vms_parse(text, cwd)
    if style == MVS and not text.startswith("/"):
        return _mvs_parse(text, cwd)
    if style == MULTICS and not text.startswith("/"):
        return _multics_parse(text, cwd)
    if style == CPM and not text.startswith("/"):
        return _cpm_parse(text, cwd)
    if style == PRIMOS and not text.startswith("/"):
        return _primos_parse(text, cwd)
    if style == MAC and not text.startswith("/"):
        return _mac_parse(text, cwd)
    return _join(cwd, text.split("/"), absolute=text.startswith("/"))


def _join(cwd, parts, absolute=False, keep=0):
    """Собрать путь: части поверх cwd (или корня), «.» пропускается, «..» поднимается, но не выше keep первых частей (диск)."""
    found = [] if absolute else [part for part in cwd.split("/") if part]
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if len(found) > keep:
                found.pop()
            continue
        found.append(part)
    return "/" + "/".join(found)


def _drive(cwd):
    first = next((part for part in cwd.split("/") if part), "")
    return first if first.endswith(":") else ""


# ---------- Windows: C:\Users\ivan ----------

def _windows_show(path):
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "\\"
    if parts[0].endswith(":"):
        return parts[0] + "\\" + "\\".join(parts[1:])
    return "\\" + "\\".join(parts)


def _windows_parse(text, cwd):
    text = text.replace("\\", "/")
    if _DRIVE_START.match(text):                                   # C:\Users или C:
        drive, rest = text[:2].upper(), text[2:]
        return _join("", [drive, *rest.split("/")], absolute=True, keep=1)
    if text.startswith("/"):                                       # \Users: от корня текущего диска
        drive = _drive(cwd)
        return _join("", [drive, *text.split("/")] if drive else text.split("/"), absolute=True, keep=1 if drive else 0)
    return _join(cwd, text.split("/"), keep=1 if _drive(cwd) else 0)


# ---------- VMS: DSK0:[OPS.IVAN]FILE.TXT;1 ----------

_VMS = re.compile(r"^(?:(?P<dev>[A-Za-z0-9$_]+):)?(?:\[(?P<dir>[^\]]*)\])?(?P<name>[^;\[\]:]*)(?:;(?P<ver>-?\d*))?$")
VMS_ROOT = "000000"


def _vms_show(path, is_dir):
    parts = [part for part in path.split("/") if part]
    device = parts.pop(0)[:-1].upper() + ":" if parts and parts[0].endswith(":") else ""
    if is_dir:
        return f"{device}[{'.'.join(parts).upper() or VMS_ROOT}]"
    name = parts.pop() if parts else ""
    return f"{device}[{'.'.join(parts).upper() or VMS_ROOT}]{name.upper()};1"


def _vms_parse(text, cwd):
    found = _VMS.match(text)
    if found is None:
        raise PathSyntax(f"bad file specification: {text}")
    device, folder, name = found.group("dev"), found.group("dir"), found.group("name")
    here = [part for part in cwd.split("/") if part]
    current = here.pop(0) if here and here[0].endswith(":") else ""
    drive = (device.upper() + ":") if device else current
    if folder is None:                                             # без [..]: в текущей папке (или в корне указанного устройства)
        base = [] if device else here
    elif folder in ("", VMS_ROOT):
        base = []
    else:
        steps = folder.split(".")
        relative = folder.startswith(".") or folder.startswith("-")
        base = list(here) if relative and not device else []
        for step in steps:
            if step == "":
                continue
            if step.strip("-") == "":                              # [-] и [--]: на уровень (уровни) вверх
                del base[len(base) - min(len(step), len(base)):]
            elif step in (".", VMS_ROOT):
                continue
            else:
                base.append(step)
    if name:
        base.append(name)
    return "/" + "/".join(([drive] if drive else []) + base)


# ---------- мейнфрейм: OPS.IVAN.DESK, 'SYS1.PARMLIB(MEMBER)' ----------

_QUALIFIER = re.compile(r"^[A-Za-z#@$][A-Za-z0-9#@$-]{0,7}$")
MVS_ROOT = "*"
MVS_MAX = 44


def _mvs_show(path):
    parts = [part for part in path.split("/") if part]
    return ".".join(parts).upper() if parts else MVS_ROOT


def _mvs_parse(text, cwd):
    """Имя в кавычках полное ('SYS1.PARMLIB'), без кавычек дописывается к текущему префиксу (папке), как в TSO.
    * это корень каталога. Член библиотеки: A.B(M) то же, что A.B.M."""
    if text == MVS_ROOT:
        return "/"
    quoted = len(text) >= 2 and text[0] == text[-1] == "'"
    name = text[1:-1] if quoted else text
    member = None
    if name.endswith(")") and "(" in name:
        name, member = name[:-1].split("(", 1)
    qualifiers = [part for part in name.split(".")] if name else []
    for qualifier in qualifiers + ([member] if member is not None else []):
        if not _QUALIFIER.match(qualifier or ""):
            raise PathSyntax(f"invalid data set name: {text}")
    if len(".".join(qualifiers)) > MVS_MAX:
        raise PathSyntax(f"data set name longer than {MVS_MAX}: {text}")
    parts = qualifiers + ([member] if member is not None else [])
    return _join(cwd, parts, absolute=quoted)



# ---------- Multics: >udd>Ops>Ivan>note ----------

def _multics_show(path):
    parts = [part for part in path.split("/") if part]
    return ">" + ">".join(parts)


def _multics_parse(text, cwd):
    """> в начале: от корня. Каждый < в начале поднимает на уровень. Остальное через > относительно текущей папки."""
    absolute = text.startswith(">")
    rest = text[1:] if absolute else text
    ups = len(rest) - len(rest.lstrip("<"))
    if absolute and ups:
        raise PathSyntax(f"incorrect pathname syntax: {text}")
    rest = rest[ups:]
    if "<" in rest or ">>" in rest or rest.endswith(">"):
        raise PathSyntax(f"incorrect pathname syntax: {text}")
    return _join(cwd, [".."] * ups + rest.split(">"), absolute=absolute)


# ---------- CP/M: A3:NOTE.TXT ----------

_CPM = re.compile(r"^(?:(?P<drive>[A-Pa-p])?(?P<user>\d{1,2})?:)?(?P<name>[^:]*)$")
_CPM_NAME = re.compile(r"^[A-Za-z0-9!#$%&'()@^_{}~-]{1,8}(?:\.[A-Za-z0-9!#$%&'()@^_{}~-]{0,3})?$")
CPM_USERS = 16


def _cpm_split(path):
    """(диск, область, остальное) канонического пути /A:/3/NOTE.TXT."""
    parts = [part for part in path.split("/") if part]
    drive = parts.pop(0)[0].upper() if parts and parts[0].endswith(":") else ""
    user = parts.pop(0) if parts and parts[0].isdigit() else "0"
    return drive, user, parts


def _cpm_area(drive, user):
    return f"{drive}{'' if user == '0' else user}:"


def _cpm_show(path):
    drive, user, rest = _cpm_split(path)
    if not drive:
        return "/" + "/".join(rest) if rest else "/"
    return _cpm_area(drive, user) + ".".join(rest[:1]).upper() + ("/" + "/".join(rest[1:]) if rest[1:] else "")


def _cpm_parse(text, cwd):
    """Папок нет: диск (A–P) и область пользователя (0–15). Без диска и области: текущие. Имя в формате 8.3."""
    found = _CPM.match(text)
    if found is None:
        raise PathSyntax(f"bad file name: {text}")
    here_drive, here_user, _ = _cpm_split(cwd)
    drive = (found.group("drive") or here_drive or "A").upper()
    user = found.group("user")
    if user is None:
        user = here_user if not found.group("drive") or drive == here_drive else "0"
    if int(user) >= CPM_USERS:
        raise PathSyntax(f"bad user area: {text}")
    name = found.group("name")
    if name and not _CPM_NAME.match(name):
        raise PathSyntax(f"bad file name: {text}")
    return "/" + "/".join(part for part in (f"{drive}:", str(int(user)), name) if part)


# ---------- PRIMOS: <DISK0>OPS>IVAN>NOTE ----------

def _primos_show(path):
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "<>"
    return f"<{parts[0].upper()}>" + ">".join(parts[1:]).upper()


def _primos_parse(text, cwd):
    """<ТОМ> в начале: от тома. * это текущая папка (*>SUB>FILE). Просто имена через > тоже от текущей папки."""
    if text.startswith("<"):
        end = text.find(">")
        if end < 2:
            raise PathSyntax(f"bad pathname: {text}")
        volume, rest = text[1:end], text[end + 1:]
        parts = [volume, *(rest.split(">") if rest else [])]
        absolute = True
    else:
        rest = text[2:] if text.startswith("*>") else ("" if text == "*" else text)
        parts, absolute = (rest.split(">") if rest else []), False
    if any(part in ("", "..") or "<" in part for part in parts):
        raise PathSyntax(f"bad pathname: {text}")
    return _join(cwd, parts, absolute=absolute)


# ---------- Classic Mac OS: Macintosh HD:System Folder:Finder ----------

MAC_DESKTOP = "Desktop"           # корень: над томами, как стол Finder


def _mac_show(path, is_dir):
    parts = [part for part in path.split("/") if part]
    if not parts:
        return MAC_DESKTOP
    text = ":".join(parts)
    return text + ":" if is_dir or len(parts) == 1 else text


def _mac_parse(text, cwd):
    """Без двоеточий: имя в текущей папке. С двоеточием в начале: от текущей папки, каждое лишнее двоеточие поднимает на уровень
    (::Other это соседняя папка). Иначе первое имя это том: Macintosh HD:System Folder. Пустое имя внутри (Disk:A::B) тоже вверх."""
    if ":" not in text:
        return _join(cwd, [text])
    relative = text.startswith(":")
    body = text[1:] if relative else text
    parts = body.split(":")
    if parts and parts[-1] == "":
        parts.pop()                                    # двоеточие в конце: это папка
    if not relative and (not parts or parts[0] == ""):
        raise PathSyntax(f"bad pathname: {text}")
    return _join(cwd, [".." if part == "" else part for part in parts], absolute=not relative)
