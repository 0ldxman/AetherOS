"""История версий записей вики.

record_revision вызывается по post_save записи и добавляет снимок, если
содержимое изменилось с прошлого раза. Сохранения без правок (например,
смена только прав доступа) историю не раздувают.
"""
from .models import DocumentRevision

# поля записи, которые попадают в снимок
SNAPSHOT_FIELDS = ("title", "type", "body", "infobox")


def snapshot(doc):
    return {name: getattr(doc, name) for name in SNAPSHOT_FIELDS}


def record_revision(doc):
    """Снимок текущего состояния записи; None, если оно совпадает с последним."""
    current = snapshot(doc)
    last = (
        DocumentRevision.objects.filter(document=doc)
        .order_by("-saved_at", "-id")
        .first()
    )
    if last is not None and snapshot(last) == current:
        return None
    return DocumentRevision.objects.create(
        document=doc, saved_by=doc.updated_by, **current
    )


def on_document_saved(sender, instance, **kwargs):
    if kwargs.get("raw"):  # загрузка фикстур: историю не трогаем
        return
    record_revision(instance)


# =========================================================
# Сравнение
# =========================================================

def diff_rows(old, new, context=3):
    """Построчная разница двух текстов -> список (вид, строка).

    Вид: "add", "del", "same" или "hunk" (заголовок блока изменений).
    Неизменённые строки дальше context от правок опускаются.
    """
    import difflib

    rows = []
    lines = difflib.unified_diff(
        old.splitlines(), new.splitlines(), n=context, lineterm=""
    )
    for line in lines:
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("@@"):
            rows.append(("hunk", line))
        elif line.startswith("+"):
            rows.append(("add", line[1:]))
        elif line.startswith("-"):
            rows.append(("del", line[1:]))
        else:
            rows.append(("same", line[1:]))
    return rows


def compare(old, new):
    """Различия между двумя снимками (или записью): словарь по полям.

    В результат попадают только изменившиеся поля.
    """
    result = {}
    for name in ("title", "type"):
        before, after = getattr(old, name), getattr(new, name)
        if before != after:
            result[name] = (before, after)
    for name in ("body", "infobox"):
        before, after = getattr(old, name), getattr(new, name)
        if before != after:
            result[name] = diff_rows(before, after)
    return result
