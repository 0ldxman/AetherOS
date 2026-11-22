"""Журнал сценария: короткие записи о том, что произошло (кто нажал на пульте, какой этап пройден, чья ветка занята)."""
import logging

from django.db import transaction

from graph.models import Entry

log = logging.getLogger(__name__)

KEEP = 1500                      # записей на сценарий: старые стираются
KINDS = {"start": "Старт", "stage": "Этап", "control": "Пульт", "branch": "Ветка", "crew": "Группа", "end": "Конец", "reset": "Сброс", "switch": "Включение"}


def name_of(user):
    return user.get_username() if user is not None else ""


def note(graph, kind, text, who="", node="", run=None):
    """Дописать запись. Сбой журнала не должен ломать ход сценария (savepoint: транзакция вокруг остаётся целой)."""
    try:
        with transaction.atomic():
            entry = Entry.objects.create(graph=graph, kind=kind, text=str(text)[:300], who=str(who or "")[:80], node=str(node or "")[:64], run=getattr(run, "pk", run))
            if entry.pk % 100 == 0:
                prune(graph)
    except Exception:                               # noqa: BLE001
        log.exception("graph journal failed")


def prune(graph, keep=KEEP):
    cut = Entry.objects.filter(graph=graph).order_by("-id").values_list("id", flat=True)[keep:keep + 1]
    if cut:
        Entry.objects.filter(graph=graph, id__lte=cut[0]).delete()


def page(graph, before=None, kind="", limit=50):
    """Страница журнала от новых к старым: записи и id, с которого просить следующую страницу (None — это всё)."""
    rows = Entry.objects.filter(graph=graph)
    if before:
        rows = rows.filter(id__lt=before)
    if kind:
        rows = rows.filter(kind=kind)
    rows = list(rows[:limit + 1])
    more = len(rows) > limit
    rows = rows[:limit]
    return rows, (rows[-1].pk if more and rows else None)
