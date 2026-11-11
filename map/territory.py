"""Территории: кто чем владел на дату. Логика правки владений для админки и Студии.

Владение это запись «провинция → страна с даты». Владелец на дату это последняя запись не позже неё; более поздние записи
продолжают действовать со своих дат, поэтому правка «с даты» их не трогает. Все изменения идут одной транзакцией.
"""
import datetime as dt

from django.db import transaction
from django.db.models import Count, F, Q

from map.models import Country, Ownership, Province

APPLY_MAX_PROVINCES = 10000
SAMPLE = 40            # сколько примеров показывает проверка


class TerritoryError(Exception):
    """Ошибка правки с кодом ответа (400 неверный запрос, 404 нет страны)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def latest(on_date=None):
    """Последнее владение каждой провинции на дату (без даты: самое свежее): {province_id: Ownership}."""
    qs = Ownership.objects.select_related("country")
    if on_date is not None:
        qs = qs.filter(date_from__lte=on_date)
    found = {}
    for row in qs.order_by("province_id", "-date_from", "-id"):
        found.setdefault(row.province_id, row)
    return found


def owners_on(on_date=None):
    """Карта для рисования: {source_code: {country, color, de_jure, de_facto}} на дату."""
    codes = dict(Province.objects.values_list("id", "source_code"))
    return {
        codes[pid]: {"country": o.country_id, "color": o.country.color, "de_jure": o.de_jure, "de_facto": o.de_facto}
        for pid, o in latest(on_date).items() if pid in codes
    }


def _codes(codes):
    if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
        raise TerritoryError("codes должен быть списком строк")
    codes = list(dict.fromkeys(codes))
    if not codes:
        raise TerritoryError("ничего не выделено")
    if len(codes) > APPLY_MAX_PROVINCES:
        raise TerritoryError(f"слишком много провинций (максимум {APPLY_MAX_PROVINCES})")
    return codes


def _history(provinces):
    """История владений провинций: {province_id: [записи от новых к старым]}."""
    found = {}
    for o in Ownership.objects.filter(province__in=provinces).order_by("province_id", "-date_from", "-id"):
        found.setdefault(o.province_id, []).append(o)
    return found


def check_life(country, on_date):
    if on_date < country.valid_from or (country.valid_to and on_date > country.valid_to):
        period = f"{country.valid_from} - {country.valid_to or '...'}"
        raise TerritoryError(f"страна {country.code} существует {period}, дата {on_date} вне этого периода")


@transaction.atomic
def apply_ownership(codes, country, on_date, de_jure=True, de_facto=True):
    """Передать провинции (source_code) стране с даты.

    Для каждой: есть запись ровно на эту дату: она обновляется; на эту дату владение уже такое же: ничего; иначе создаётся запись.
    -> {created, updated, unchanged, later, missing}"""
    codes = _codes(codes)
    if not (de_jure or de_facto):
        raise TerritoryError("нужно выбрать de jure или de facto")
    check_life(country, on_date)

    provinces = {p.source_code: p for p in Province.objects.filter(source_code__in=codes)}
    missing = [c for c in codes if c not in provinces]
    history = _history(provinces.values())
    wanted = (country.pk, de_jure, de_facto)
    to_create, to_update = [], []
    unchanged = later = 0
    for province in provinces.values():
        rows = history.get(province.pk, [])
        exact = next((o for o in rows if o.date_from == on_date), None)
        current = next((o for o in rows if o.date_from <= on_date), None)
        if any(o.date_from > on_date for o in rows):
            later += 1
        if exact is not None:
            if (exact.country_id, exact.de_jure, exact.de_facto) == wanted:
                unchanged += 1
            else:
                exact.country = country
                exact.de_jure, exact.de_facto = de_jure, de_facto
                to_update.append(exact)
        elif current is not None and (current.country_id, current.de_jure, current.de_facto) == wanted:
            unchanged += 1
        else:
            to_create.append(Ownership(province=province, country=country, date_from=on_date, de_jure=de_jure, de_facto=de_facto))
    Ownership.objects.bulk_create(to_create)
    Ownership.objects.bulk_update(to_update, ["country", "de_jure", "de_facto"])
    return {"created": len(to_create), "updated": len(to_update), "unchanged": unchanged, "later": later, "missing": missing}


@transaction.atomic
def erase_ownership(codes, on_date):
    """Убрать записи владения, начатые ровно в эту дату (ластик): провинция возвращается к прежнему владельцу.
    -> {deleted, none} (none: провинций, у которых на эту дату записи не было)."""
    codes = _codes(codes)
    provinces = list(Province.objects.filter(source_code__in=codes))
    rows = Ownership.objects.filter(province__in=provinces, date_from=on_date)
    touched = set(rows.values_list("province_id", flat=True))
    deleted = rows.count()
    rows.delete()
    return {"deleted": deleted, "none": len(provinces) - len(touched)}


def provinces_of(country, on_date=None):
    """source_code провинций, которыми страна владеет на дату."""
    codes = dict(Province.objects.values_list("id", "source_code"))
    return [codes[pid] for pid, o in latest(on_date).items() if o.country_id == country.pk and pid in codes]


def transfer_country(source, target, on_date, de_jure=True, de_facto=True):
    """Передать всё, чем страна владеет на дату, другой стране с этой даты (присоединение, наследование)."""
    if source.pk == target.pk:
        raise TerritoryError("страна уже владеет этим")
    codes = provinces_of(source, on_date)
    if not codes:
        raise TerritoryError(f"на {on_date} у страны {source.code} нет провинций")
    return {**apply_ownership(codes, target, on_date, de_jure, de_facto), "moved": len(codes)}


def province_info(province, on_date=None):
    """Владелец на дату и вся история провинции (от новых записей к старым)."""
    rows = list(Ownership.objects.filter(province=province).select_related("country").order_by("-date_from", "-id"))
    current = next((o for o in rows if on_date is None or o.date_from <= on_date), None)
    return {
        "owner": current,
        "history": [(o, o is current) for o in rows],
    }


def _no_owner():
    owned = set(Ownership.objects.values_list("province_id", flat=True))
    return [{"kind": "province", "id": p.pk, "label": f"{p.name} ({p.code})", "province_id": p.pk}
            for p in Province.objects.exclude(pk__in=owned).order_by("name")]


def _outside_life():
    outside = Ownership.objects.select_related("province", "country").filter(
        Q(date_from__lt=F("country__valid_from")) | Q(country__valid_to__isnull=False, date_from__gt=F("country__valid_to"))
    ).order_by("country__code", "date_from")
    return [{"kind": "ownership", "id": o.pk, "label": f"{o.province.code} → {o.country.code} с {o.date_from}",
             "province_id": o.province_id, "country_id": o.country_id} for o in outside]


def _same_day():
    dup = Ownership.objects.values("province_id", "date_from").annotate(n=Count("id")).filter(n__gt=1).order_by("date_from")
    names = dict(Province.objects.filter(pk__in=[d["province_id"] for d in dup]).values_list("id", "code"))
    return [{"kind": "province", "id": d["province_id"], "label": f"{names.get(d['province_id'], '?')} на {d['date_from']}", "province_id": d["province_id"]}
            for d in dup]


def _dead_owner():
    return [{"kind": "province", "id": pid, "label": f"{o.province.code}: {o.country.code} закончилась {o.country.valid_to}",
             "province_id": pid, "country_id": o.country_id}
            for pid, o in latest_with_province().items() if o.country.valid_to is not None]


def _idle_country():
    return [{"kind": "country", "id": c.pk, "label": f"{c.name} ({c.code})", "country_id": c.pk}
            for c in Country.objects.filter(owned_provinces__isnull=True).order_by("name")]


def _no_label():
    return [{"kind": "country", "id": c.pk, "label": f"{c.name} ({c.code})", "country_id": c.pk}
            for c in Country.objects.filter(owned_provinces__isnull=False, labels__isnull=True).distinct().order_by("name")]


# код проверки: (уровень, название, функция находок); порядок задаёт порядок на экране
CHECKS = {
    "no-owner": ("warning", "Провинции без единого владельца", _no_owner),
    "outside-life": ("error", "Владение вне лет жизни страны", _outside_life),
    "same-day": ("error", "Провинция записана двум странам на одну дату", _same_day),
    "dead-owner": ("warning", "Последний владелец уже не существует", _dead_owner),
    "idle-country": ("info", "Страны без единого владения", _idle_country),
    "no-label": ("info", "Страны с владениями, но без подписи", _no_label),
}


def checks():
    """Что в данных карты выглядит неправильно: список {code, level, title, count, items} (items не больше SAMPLE).
    Проверки без находок не попадают в список."""
    found = []
    for code, (level, title, run) in CHECKS.items():
        rows = run()
        if rows:
            found.append({"code": code, "level": level, "title": title, "count": len(rows), "items": rows[:SAMPLE]})
    return found


def check_items(code, query="", offset=0, limit=50):
    """Находки одной проверки целиком, с поиском по тексту: {total, rows}. Неизвестный код это 404."""
    if code not in CHECKS:
        raise TerritoryError("Такой проверки нет.", 404)
    rows = CHECKS[code][2]()
    text = query.strip().lower()
    if text:
        rows = [row for row in rows if text in row["label"].lower()]
    limit = max(1, min(limit, 200))
    return {"total": len(rows), "rows": rows[max(0, offset):max(0, offset) + limit]}


def latest_with_province():
    found = {}
    for o in Ownership.objects.select_related("country", "province").order_by("province_id", "-date_from", "-id"):
        found.setdefault(o.province_id, o)
    return found
