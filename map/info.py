"""Карточка провинции для приложения карты: владелец на дату, история владений, страна и материал (объект), который игрок может открыть.

Одни и те же данные показывают боковая панель (карта на весь экран) и отдельное окно-инфобокс (карта в iframe рабочего стола).
Что показывать, решает автор: флаг show_info у провинции (нет карточки совсем) и у страны (нет блока страны и её материала)."""
import datetime as dt

from django.urls import reverse

from map import territory
from map.models import Country, Ownership, Province


def _flags(ownership):
    if ownership.de_jure and ownership.de_facto:
        return "де-юре и де-факто"
    return "де-юре" if ownership.de_jure else "де-факто"


def _material(request, item):
    """Объект, который игрок вправе открыть: он есть в вики его машины (том смонтирован, запись видна). Иначе None."""
    if item is None or request is None:
        return None
    from secure.requestkeys import request_keys
    from wiki.access import document_state
    from wiki.views import library

    try:
        page = library(request).by_slug.get(item.slug)
        if page is None or not document_state(page, request_keys(request), via_direct_link=True).visible:
            return None
    except Exception:                       # у запроса нет машины игрока (просмотр автором без сессии): материал не показываем
        return None
    return {"title": item.name, "url": reverse("wiki:direct", args=[item.slug])}


def _external(*urls):
    for raw in urls:
        raw = (raw or "").strip()
        if raw.startswith(("http://", "https://")) or (raw.startswith("/") and not raw.startswith("//")):
            return raw
    return ""


def card(request, source_code, on_date=None):
    """Данные карточки или None, если провинции нет или автор скрыл карточку."""
    province = Province.objects.select_related("material").filter(source_code=source_code).first()
    if province is None or not province.show_info:
        return None
    rows = list(Ownership.objects.filter(province=province).select_related("country").order_by("date_from", "id"))
    on = on_date or (rows[-1].date_from if rows else None)
    current = None
    for row in rows:
        if on is None or row.date_from <= on:
            current = row
    history = [
        {"date_from": row.date_from, "name": row.country.name, "code": row.country.code, "color": row.country.color, "rights": _flags(row),
         "current": row is current, "future": on is not None and row.date_from > on}
        for row in reversed(rows)
    ]
    owner = None
    country = None
    if current is not None:
        owner = {"name": current.country.name, "code": current.country.code, "color": current.country.color, "since": current.date_from, "rights": _flags(current)}
        c = current.country
        if c.show_info:
            owned = sum(1 for o in territory.latest(on).values() if o.country_id == c.pk)
            country = {
                "name": c.name, "code": c.code, "color": c.color, "valid_from": c.valid_from, "valid_to": c.valid_to,
                "predecessor": c.predecessor.name if c.predecessor_id else "",
                "successors": list(c.successors.order_by("name").values_list("name", flat=True)),
                "provinces": owned,
            }
    material = _material(request, province.material)
    if material is None and country is not None:
        material = _material(request, current.country.material)
    link = ""
    if material is None:
        link = _external(province.wiki_url, current.country.wiki_url if country is not None and current is not None else "")
    return {
        "province": {"name": province.name, "code": province.code, "source_code": province.source_code},
        "date": on, "owner": owner, "history": history, "country": country, "material": material, "link": link,
    }
