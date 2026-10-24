"""Экспорт и импорт записей вики в виде архива markdown-файлов.

Раскладка архива повторяет дерево разделов:

    Тех/
      _section.yml          метаданные раздела (slug, access, visibility)
      Оружие/
        _section.yml
        Винтовка.md         текст записи с блоком метаданных в начале
        Винтовка.infobox.md инфобокс (если он есть)
    Корень.md               запись без раздела

Блок метаданных в начале .md-файла:

    ---
    type: doc
    direct_link: rifle
    access: key_beta
    visibility: {"any": ["key_a", "key_b"]}
    ---
    Текст записи…

Значение после «ключ: » читается как JSON, если начинается с кавычки,
«[» или «{», иначе как строка. Поэтому условия доступа (словари) пишутся
JSON'ом, а slug ключа и прочие простые значения просто словом. Название записи берётся из имени
файла; символы, недопустимые в именах файлов (/ \\ : * ? " < > | %), и точка
в начале имени записываются как %XX.

Правила импорта:
- запись ищется по пути (раздел + название): найденная обновляется,
  остальные создаются; ничего не удаляется;
- если в файле есть блок метаданных, отсутствующий в нём ключ означает
  «пусто»; файл без блока меняет только текст;
- инфобокс меняется, только если в архиве есть .infobox.md;
- переводы строк при сравнении не учитываются (браузер сохраняет \\r\\n).

Сухой прогон и настоящий импорт выполняет один и тот же код (run): прогон
идёт в транзакции, которая откатывается. Поэтому всё, что он показывает,
проверено теми же проверками, что и сама запись.
"""
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import unquote

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .markup.lint import lint
from .models import Document, Namespace

MAX_ARCHIVE_BYTES = 10 * 1024 * 1024    # сам загруженный файл
MAX_UNPACKED_BYTES = 40 * 1024 * 1024   # всё содержимое после распаковки
MAX_FILE_BYTES = 2 * 1024 * 1024        # один файл
MAX_FILES = 3000
MAX_WARNINGS_SHOWN = 5                  # замечаний линтера на запись в таблице

SECTION_FILE = "_section.yml"
INFOBOX_SUFFIX = ".infobox.md"
DOC_SUFFIX = ".md"

SECTION_KEYS = ("slug", "access", "visibility")
DOC_KEYS = ("type", "direct_link", "access", "visibility")

_UNSAFE = '/\\:*?"<>|%'
_BARE = re.compile(r"[A-Za-z0-9_.-]+")


class ArchiveError(Exception):
    """Архив нельзя прочитать вообще (не тот формат, слишком большой)."""


# =========================================================
# Имена файлов и значения
# =========================================================

def encode_name(name):
    """Название -> безопасное имя файла или папки."""
    out = "".join(f"%{ord(c):02X}" if c in _UNSAFE else c for c in name)
    if out.startswith("."):
        out = "%2E" + out[1:]
    return out


def decode_name(name):
    return unquote(name)


def emit_value(value):
    """Значение метаданных -> текст после «ключ: »."""
    if isinstance(value, str):
        if _BARE.fullmatch(value):
            return value
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def parse_value(text):
    """Текст после «ключ: » -> значение: JSON, если начинается с " [ {, иначе строка."""
    text = text.strip()
    if text[:1] in ('"', "[", "{"):
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ValueError(f"не получилось прочитать значение {text!r}: {exc}") from None
    return text


def parse_meta_lines(lines, allowed):
    """Строки «ключ: значение» -> (словарь, замечания). ValueError на неверной строке."""
    meta, warnings = {}, []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        key = key.strip()
        if not sep:
            raise ValueError(f"строка метаданных без «:»: {line!r}")
        if key not in allowed:
            warnings.append(f"неизвестный ключ «{key}» пропущен")
            continue
        meta[key] = parse_value(value)
    return meta, warnings


def split_front_matter(text):
    """Текст файла -> (строки метаданных или None, остаток текста)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index], "".join(lines[index + 1:])
    raise ValueError("блок метаданных не закрыт строкой «---»")


# =========================================================
# Экспорт
# =========================================================

def _meta_lines(pairs):
    return "".join(f"{key}: {emit_value(value)}\n" for key, value in pairs if value not in ("", {}, None))


def build_archive(documents, namespaces):
    """ZIP-архив из записей и разделов (оба списка объектов моделей).

    Папки создаются и для предков разделов выбранных записей, чтобы путь
    восстановился целиком.
    """
    by_id = {n.pk: n for n in Namespace.objects.all()}

    def chain(ns_id):
        names = []
        while ns_id is not None:
            node = by_id[ns_id]
            names.append(node)
            ns_id = node.parent_id
        return names[::-1]

    wanted = {}
    for ns in list(namespaces) + [by_id[d.namespace_id] for d in documents if d.namespace_id]:
        for node in chain(ns.pk):
            wanted[node.pk] = node

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        def write(path, text, stamp=None):
            info = zipfile.ZipInfo(path, date_time=(stamp or datetime(2020, 1, 1)).timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text.encode("utf-8"))

        def folder(ns_id):
            return "".join(encode_name(n.name) + "/" for n in chain(ns_id)) if ns_id else ""

        for ns in sorted(wanted.values(), key=lambda n: n.pk):
            body = _meta_lines([("slug", ns.slug), ("access", ns.access), ("visibility", ns.visibility)])
            write(folder(ns.pk) + SECTION_FILE, body)

        for doc in documents:
            path = folder(doc.namespace_id) + encode_name(doc.title)
            head = _meta_lines(
                [
                    ("type", doc.type),
                    ("direct_link", doc.direct_link),
                    ("access", doc.access),
                    ("visibility", doc.visibility),
                ]
            )
            write(path + DOC_SUFFIX, f"---\n{head}---\n{doc.body}", doc.updated_at)
            if doc.infobox:
                write(path + INFOBOX_SUFFIX, doc.infobox, doc.updated_at)

    return buffer.getvalue()


def subtree_ids(namespace_id):
    """id раздела и всех вложенных."""
    children = {}
    for pk, parent in Namespace.objects.values_list("pk", "parent_id"):
        children.setdefault(parent, []).append(pk)
    found, stack = [], [namespace_id]
    while stack:
        current = stack.pop()
        found.append(current)
        stack.extend(children.get(current, []))
    return found


# =========================================================
# Чтение архива
# =========================================================

@dataclass
class SourceDoc:
    path: tuple             # цепочка разделов
    title: str
    body: str = ""
    has_body: bool = False  # был ли файл записи .md (а не только .infobox.md)
    meta: dict = None       # None: блока метаданных в файле не было
    infobox: str = None     # None: файла .infobox.md не было
    warnings: list = field(default_factory=list)
    error: str = ""


@dataclass
class SourceSection:
    path: tuple
    meta: dict
    warnings: list = field(default_factory=list)
    error: str = ""


@dataclass
class Archive:
    docs: dict = field(default_factory=dict)        # (path, title) -> SourceDoc
    sections: dict = field(default_factory=dict)    # path -> SourceSection
    notes: list = field(default_factory=list)       # замечания к архиву в целом


def _zip_name(info):
    name = info.filename
    if not info.flag_bits & 0x800:
        # архиваторы без флага UTF-8 пишут кириллицу как UTF-8 байтами, а читается cp437
        try:
            name = name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def _text(data):
    return data.decode("utf-8-sig")


def _read_doc(archive, path, title, text):
    key = (path, title)
    source = archive.docs.setdefault(key, SourceDoc(path, title))
    try:
        lines, body = split_front_matter(text)
        if lines is not None:
            source.meta, source.warnings = parse_meta_lines(lines, DOC_KEYS)
        source.body = body
        source.has_body = True
        if source.meta and "type" in source.meta and source.meta["type"] not in Document.Type.values:
            raise ValueError(f"неизвестный тип «{source.meta['type']}»")
    except ValueError as exc:
        source.error = str(exc)


def read_archive(data, filename=""):
    """Байты загруженного файла -> Archive. ArchiveError, если файл не годится."""
    if not data:
        raise ArchiveError("Файл пустой.")
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveError(f"Файл больше {MAX_ARCHIVE_BYTES // 1024 // 1024} МБ.")

    archive = Archive()

    if not zipfile.is_zipfile(io.BytesIO(data)):
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        title = decode_name(re.sub(r"\.md$", "", filename, flags=re.I))
        if not title or not filename.lower().endswith(DOC_SUFFIX):
            raise ArchiveError("Нужен ZIP-архив или файл .md.")
        try:
            _read_doc(archive, (), title, _text(data))
        except UnicodeDecodeError:
            raise ArchiveError("Файл не в кодировке UTF-8.") from None
        return archive

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = [i for i in zf.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        raise ArchiveError("Архив повреждён.") from None
    if len(infos) > MAX_FILES:
        raise ArchiveError(f"В архиве больше {MAX_FILES} файлов.")
    if sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
        raise ArchiveError("Содержимое архива слишком велико.")

    for info in infos:
        name = _zip_name(info).replace("\\", "/")
        parts = [p for p in name.split("/") if p]
        if ".." in parts:
            archive.notes.append(f"{name}: пропущен (недопустимый путь)")
            continue
        if not parts or any(p.startswith((".", "__MACOSX")) for p in parts):
            continue  # служебные и скрытые файлы
        if info.file_size > MAX_FILE_BYTES:
            archive.notes.append(f"{name}: пропущен (больше {MAX_FILE_BYTES // 1024 // 1024} МБ)")
            continue
        last = parts[-1]
        path = tuple(decode_name(p) for p in parts[:-1])
        try:
            text = _text(zf.read(info))
        except UnicodeDecodeError:
            archive.notes.append(f"{name}: пропущен (не UTF-8)")
            continue

        if last == SECTION_FILE:
            section = SourceSection(path, {})
            try:
                lines = text.splitlines()
                section.meta, section.warnings = parse_meta_lines(lines, SECTION_KEYS)
            except ValueError as exc:
                section.error = str(exc)
            archive.sections[path] = section
        elif last.lower().endswith(INFOBOX_SUFFIX):
            title = decode_name(last[: -len(INFOBOX_SUFFIX)])
            archive.docs.setdefault((path, title), SourceDoc(path, title)).infobox = text
        elif last.lower().endswith(DOC_SUFFIX):
            title = decode_name(last[: -len(DOC_SUFFIX)])
            if (path, title) in archive.docs and archive.docs[(path, title)].has_body:
                archive.notes.append(f"{name}: повтор записи в архиве, взят первый файл")
                continue
            _read_doc(archive, path, title, text)
        else:
            archive.notes.append(f"{name}: пропущен (ожидаются .md и {SECTION_FILE})")

    return archive


# =========================================================
# Выполнение
# =========================================================

@dataclass
class Row:
    kind: str               # "section" | "doc"
    path: str
    action: str             # "create" | "update" | "same" | "error"
    changes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def _norm(text):
    return (text or "").replace("\r\n", "\n")


def _errors(exc):
    messages = getattr(exc, "messages", None)
    return list(messages) if messages else [str(exc)]


def _label(path, title=None):
    parts = list(path) + ([title] if title else [])
    return ":".join(parts) if parts else "~"


def _save(obj, exclude):
    """full_clean + save в своей точке сохранения: ошибка не ломает остальной импорт."""
    with transaction.atomic():
        obj.full_clean(exclude=exclude)
        obj.save()


def _section_meta(section, existing):
    """Метаданные раздела из файла; без файла для существующего раздела: без изменений."""
    if section is None or section.error:
        return None if existing is not None else {"slug": "", "access": {}, "visibility": {}}
    meta = section.meta
    return {
        "slug": str(meta.get("slug", "")),
        "access": meta.get("access") or {},
        "visibility": meta.get("visibility") or {},
    }


def _apply_namespace(path, parent, existing, archive, rows):
    """Раздел по пути: создать или обновить. Возвращает объект или None при ошибке."""
    section = archive.sections.get(path)
    label = _label(path)

    if section is not None and section.error:
        rows.append(Row("section", label, "error", errors=[f"{SECTION_FILE}: {section.error}"]))
        return existing

    wanted = _section_meta(section, existing)
    if existing is None:
        ns = Namespace(name=path[-1], parent=parent, **wanted)
        try:
            _save(ns, exclude=None)
        except (ValidationError, IntegrityError) as exc:
            rows.append(Row("section", label, "error", errors=_errors(exc)))
            return None
        rows.append(Row("section", label, "create", warnings=list(section.warnings) if section else []))
        return ns

    if wanted is None:
        return existing
    changes = [k for k in SECTION_KEYS if getattr(existing, k) != wanted[k] and (getattr(existing, k) or wanted[k])]
    if not changes:
        return existing
    for key in changes:
        setattr(existing, key, wanted[key])
    try:
        _save(existing, exclude=None)
    except (ValidationError, IntegrityError) as exc:
        rows.append(Row("section", label, "error", errors=_errors(exc)))
        existing.refresh_from_db()
        return existing
    rows.append(Row("section", label, "update", changes=changes, warnings=list(section.warnings)))
    return existing


def _doc_values(source, existing):
    """Что файл хочет записать в запись: словарь полей."""
    meta = source.meta
    values = {"body": source.body} if source.has_body else {}
    if meta is not None:
        values.update(
            type=meta.get("type") or Document.Type.DOC,
            direct_link=str(meta.get("direct_link", "")),
            access=meta.get("access") or {},
            visibility=meta.get("visibility") or {},
        )
    elif existing is None:
        values.update(type=Document.Type.DOC, direct_link="", access={}, visibility={})
    if source.infobox is not None:
        values["infobox"] = source.infobox
    return values


def _differs(field_name, old, new):
    if field_name in ("body", "infobox"):
        return _norm(old) != _norm(new)
    return old != new and bool(old or new)


def _apply_doc(source, namespace, existing, user, rows):
    label = _label(source.path, source.title)
    if source.error:
        rows.append(Row("doc", label, "error", errors=[source.error]))
        return
    values = _doc_values(source, existing)
    exclude = ["created_by", "updated_by"]

    if existing is None:
        doc = Document(
            namespace=namespace, title=source.title, created_by=user, updated_by=user, **values
        )
        action, changes = "create", []
    else:
        changes = [k for k, v in values.items() if _differs(k, getattr(existing, k), v)]
        if not changes:
            rows.append(Row("doc", label, "same"))
            return
        doc = existing
        for key in changes:
            setattr(doc, key, values[key])
        doc.updated_by = user
        action = "update"

    try:
        _save(doc, exclude=exclude)
    except (ValidationError, IntegrityError) as exc:
        rows.append(Row("doc", label, "error", errors=_errors(exc)))
        return

    issues = lint(doc.body) + lint(doc.infobox)
    warnings = list(source.warnings) + [
        f"{i.message}" for i in issues[:MAX_WARNINGS_SHOWN]
    ]
    if len(issues) > MAX_WARNINGS_SHOWN:
        warnings.append(f"…и ещё замечаний линтера: {len(issues) - MAX_WARNINGS_SHOWN}")
    rows.append(Row("doc", label, action, changes=changes, warnings=warnings))


def execute(archive, user):
    """Записывает архив в базу и возвращает строки отчёта. Вызывать внутри run."""
    rows = []
    namespaces = {(n.parent_id, n.name): n for n in Namespace.objects.all()}
    docs = {(d.namespace_id, d.title): d for d in Document.objects.all()}

    needed = set(archive.sections)
    for path, _ in archive.docs:
        needed.update(path[: i + 1] for i in range(len(path)))
    resolved = {(): None}
    failed = set()

    for path in sorted(needed, key=lambda p: (len(p), p)):
        if not path:
            continue
        parent = resolved.get(path[:-1])
        if path[:-1] in failed or (path[:-1] and parent is None):
            failed.add(path)
            if path in archive.sections:
                rows.append(Row("section", _label(path), "error", errors=["не создан раздел выше"]))
            continue
        existing = namespaces.get((parent.pk if parent else None, path[-1]))
        ns = _apply_namespace(path, parent, existing, archive, rows)
        if ns is None:
            failed.add(path)
        else:
            resolved[path] = ns
            namespaces[(parent.pk if parent else None, path[-1])] = ns

    for (path, title), source in sorted(archive.docs.items()):
        if path in failed:
            rows.append(Row("doc", _label(path, title), "error", errors=["раздел не создан"]))
            continue
        namespace = resolved[path]
        existing = docs.get((namespace.pk if namespace else None, title))
        if existing is None and not source.has_body:
            rows.append(Row("doc", _label(path, title), "error", errors=["есть инфобокс, но нет файла записи .md"]))
            continue
        _apply_doc(source, namespace, existing, user, rows)

    return rows


def run(archive, user, commit):
    """Сухой прогон (commit=False: всё откатывается) или настоящий импорт."""
    with transaction.atomic():
        rows = execute(archive, user)
        if not commit:
            transaction.set_rollback(True)
    return rows


def summary(rows):
    """Сколько строк каждого действия: {"create": 3, "update": 1, ...} для записей и разделов."""
    counts = {"create": 0, "update": 0, "same": 0, "error": 0}
    for row in rows:
        counts[row.action] += 1
    return counts
