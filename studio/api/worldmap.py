"""Карта: страны и их подписи, провинции, владения, правка территорий на дату и проверка данных.

Логика правки владений живёт в map.territory (её же зовёт старая админка), здесь только схемы и коды ответов.
Сцены карты лежат в studio/api/mapscenes.py.
"""
import datetime as dt

from django.core.exceptions import ValidationError
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from map import territory
from map.bounds import bounds_of
from map.models import Country, CountryLabel, Ownership, Province

router = Router(tags=["map"])

COUNTRY_FIELDS = ("code", "name", "color", "valid_from", "valid_to", "wiki_url")
PAGE = 100


# ---------- страны и подписи ----------

class MapLabelOut(Schema):
    id: int
    country: int
    country_name: str
    text: str
    lng: float
    lat: float
    rank: int


class MapLabelIn(Schema):
    text: str = ""
    lng: float
    lat: float
    rank: int = 2


class MapCountryRow(Schema):
    id: int
    code: str
    name: str
    color: str
    valid_from: dt.date
    valid_to: dt.date | None
    predecessor: int | None
    predecessor_name: str
    provinces: int           # провинций сейчас (по последним записям)
    ownerships: int
    labels: int


class MapCountryOut(MapCountryRow):
    wiki_url: str
    successors: list[str]
    successor_ids: list[int]
    label_list: list[MapLabelOut]


class MapCountryIn(Schema):
    code: str
    name: str
    color: str = "#cccccc"
    valid_from: dt.date
    valid_to: dt.date | None = None
    predecessor: int | None = None
    wiki_url: str = ""


def _label(label):
    return MapLabelOut(id=label.pk, country=label.country_id, country_name=label.country.name, text=label.text, lng=label.lng, lat=label.lat, rank=label.rank)


def _row(country, now, counts):
    return {
        "id": country.pk, "code": country.code, "name": country.name, "color": country.color,
        "valid_from": country.valid_from, "valid_to": country.valid_to,
        "predecessor": country.predecessor_id, "predecessor_name": country.predecessor.name if country.predecessor_id else "",
        "provinces": now.get(country.pk, 0), "ownerships": country.n_own, "labels": country.n_labels,
    }


def _now():
    counts = {}
    for owner in territory.latest().values():
        counts[owner.country_id] = counts.get(owner.country_id, 0) + 1
    return counts


def _countries():
    return Country.objects.select_related("predecessor").annotate(
        n_own=Count("owned_provinces", distinct=True), n_labels=Count("labels", distinct=True)
    )


@router.get("/countries", response=list[MapCountryRow])
def countries(request, q: str = ""):
    rows = _countries().order_by("name")
    if q.strip():
        rows = rows.filter(Q(name__icontains=q.strip()) | Q(code__icontains=q.strip()))
    now = _now()
    return [MapCountryRow(**_row(c, now, None)) for c in rows]


def _country_out(country):
    country = _countries().get(pk=country.pk)
    successors = list(country.successors.order_by("name").values_list("name", "pk"))
    return MapCountryOut(
        **_row(country, _now(), None), wiki_url=country.wiki_url,
        successors=[name for name, _ in successors], successor_ids=[pk for _, pk in successors],
        label_list=[_label(label) for label in country.labels.select_related("country")],
    )


def _save_country(country, body):
    for name in COUNTRY_FIELDS:
        setattr(country, name, getattr(body, name))
    country.predecessor = Country.objects.filter(pk=body.predecessor).first() if body.predecessor else None
    if country.predecessor_id and country.predecessor_id == country.pk:
        raise ValidationError({"predecessor": ["Страна не может быть своим предшественником."]})
    country.full_clean()
    country.save()
    return _country_out(country)


@router.get("/countries/{int:country_id}", response=MapCountryOut)
def read_country(request, country_id: int):
    return _country_out(get_object_or_404(Country, pk=country_id))


@router.post("/countries", response=MapCountryOut)
def create_country(request, body: MapCountryIn):
    return _save_country(Country(), body)


@router.put("/countries/{int:country_id}", response=MapCountryOut)
def save_country(request, country_id: int, body: MapCountryIn):
    return _save_country(get_object_or_404(Country, pk=country_id), body)


@router.delete("/countries/{int:country_id}")
def delete_country(request, country_id: int):
    country = get_object_or_404(Country, pk=country_id)
    try:
        country.delete()
    except ProtectedError:
        raise ValidationError("У страны есть владения: сначала передайте её провинции другой стране или удалите записи.")
    return {}


@router.get("/labels", response=list[MapLabelOut])
def labels(request, q: str = "", country: int | None = None):
    rows = CountryLabel.objects.select_related("country").order_by("country__name", "rank", "id")
    if country:
        rows = rows.filter(country_id=country)
    if q.strip():
        rows = rows.filter(Q(text__icontains=q.strip()) | Q(country__name__icontains=q.strip()))
    return [_label(label) for label in rows[:500]]


def _save_label(label, body):
    label.text, label.lng, label.lat, label.rank = body.text, body.lng, body.lat, body.rank
    label.full_clean()
    label.save()
    return _label(label)


@router.post("/countries/{int:country_id}/labels", response=MapLabelOut)
def create_label(request, country_id: int, body: MapLabelIn):
    return _save_label(CountryLabel(country=get_object_or_404(Country, pk=country_id)), body)


@router.put("/labels/{int:label_id}", response=MapLabelOut)
def save_label(request, label_id: int, body: MapLabelIn):
    return _save_label(get_object_or_404(CountryLabel.objects.select_related("country"), pk=label_id), body)


@router.delete("/labels/{int:label_id}")
def delete_label(request, label_id: int):
    get_object_or_404(CountryLabel, pk=label_id).delete()
    return {}


# ---------- провинции ----------

class MapOwnerRef(Schema):
    country: int
    country_name: str
    color: str
    since: dt.date
    de_jure: bool
    de_facto: bool


class MapProvinceRow(Schema):
    id: int
    bounds: list[float] | None = None     # рамка [запад, юг, восток, север] для перехода камеры
    code: str
    source_code: str
    name: str
    wiki_url: str
    owner: MapOwnerRef | None
    records: int


class MapProvincePage(Schema):
    total: int
    rows: list[MapProvinceRow]


class MapProvinceIn(Schema):
    code: str
    source_code: str
    name: str
    wiki_url: str = ""


class MapHistoryRow(Schema):
    id: int
    date_from: dt.date
    country: int
    country_name: str
    country_code: str
    color: str
    de_jure: bool
    de_facto: bool
    current: bool


class MapProvinceOut(MapProvinceRow):
    history: list[MapHistoryRow]


def _owner(o):
    if o is None:
        return None
    return MapOwnerRef(country=o.country_id, country_name=o.country.name, color=o.country.color, since=o.date_from, de_jure=o.de_jure, de_facto=o.de_facto)


@router.get("/provinces", response=MapProvincePage)
def provinces(request, q: str = "", owner: str = "", on: dt.date | None = None, offset: int = 0, limit: int = PAGE):
    """owner: id страны или none (без владельца); on: на какую дату считать владельца."""
    rows = Province.objects.annotate(records=Count("ownerships")).order_by("name", "id")
    if q.strip():
        rows = rows.filter(Q(name__icontains=q.strip()) | Q(code__icontains=q.strip()) | Q(source_code__icontains=q.strip()))
    now = territory.latest(on)
    if owner == "none":
        rows = rows.exclude(pk__in=list(now))
    elif owner.isdigit():
        rows = rows.filter(pk__in=[pid for pid, o in now.items() if o.country_id == int(owner)])
    total = rows.count()
    page = list(rows[max(offset, 0): max(offset, 0) + min(max(limit, 1), 500)])
    return MapProvincePage(total=total, rows=[
        MapProvinceRow(id=p.pk, bounds=bounds_of(p.source_code), code=p.code, source_code=p.source_code, name=p.name, wiki_url=p.wiki_url, owner=_owner(now.get(p.pk)), records=p.records)
        for p in page
    ])


def _province_out(province, on):
    info = territory.province_info(province, on)
    now = info["owner"]
    return MapProvinceOut(
        id=province.pk, bounds=bounds_of(province.source_code), code=province.code, source_code=province.source_code, name=province.name, wiki_url=province.wiki_url,
        owner=_owner(now), records=len(info["history"]),
        history=[
            MapHistoryRow(id=o.pk, date_from=o.date_from, country=o.country_id, country_name=o.country.name, country_code=o.country.code,
                          color=o.country.color, de_jure=o.de_jure, de_facto=o.de_facto, current=current)
            for o, current in info["history"]
        ],
    )


@router.get("/provinces/{int:province_id}", response=MapProvinceOut)
def read_province(request, province_id: int, on: dt.date | None = None):
    return _province_out(get_object_or_404(Province, pk=province_id), on)


@router.get("/provinces/by-code/{source_code}", response=MapProvinceOut)
def province_by_code(request, source_code: str, on: dt.date | None = None):
    """Провинция по коду из тайлов (то, что отдаёт клик по карте)."""
    return _province_out(get_object_or_404(Province, source_code=source_code), on)


def _save_province(province, body):
    for name in ("code", "source_code", "name", "wiki_url"):
        setattr(province, name, getattr(body, name))
    province.full_clean()
    province.save()
    return _province_out(province, None)


@router.post("/provinces", response=MapProvinceOut)
def create_province(request, body: MapProvinceIn):
    return _save_province(Province(), body)


@router.put("/provinces/{int:province_id}", response=MapProvinceOut)
def save_province(request, province_id: int, body: MapProvinceIn):
    return _save_province(get_object_or_404(Province, pk=province_id), body)


@router.delete("/provinces/{int:province_id}")
def delete_province(request, province_id: int):
    get_object_or_404(Province, pk=province_id).delete()      # записи владения уходят вместе с ней
    return {}


# ---------- владения ----------

class MapOwnershipRow(Schema):
    id: int
    province: int
    province_name: str
    province_code: str
    country: int
    country_name: str
    country_code: str
    color: str
    date_from: dt.date
    de_jure: bool
    de_facto: bool


class MapOwnershipPage(Schema):
    total: int
    rows: list[MapOwnershipRow]


class MapOwnershipIn(Schema):
    province: int
    country: int
    date_from: dt.date
    de_jure: bool = True
    de_facto: bool = True


class MapIds(Schema):
    ids: list[int]


def _ownership(o):
    return MapOwnershipRow(
        id=o.pk, province=o.province_id, province_name=o.province.name, province_code=o.province.code, country=o.country_id,
        country_name=o.country.name, country_code=o.country.code, color=o.country.color, date_from=o.date_from, de_jure=o.de_jure, de_facto=o.de_facto,
    )


@router.get("/ownerships", response=MapOwnershipPage)
def ownerships(request, q: str = "", country: int | None = None, province: int | None = None, after: dt.date | None = None,
               before: dt.date | None = None, flag: str = "", offset: int = 0, limit: int = PAGE):
    """flag: jure | facto | split (только де-юре, только де-факто)."""
    rows = Ownership.objects.select_related("province", "country").order_by("-date_from", "province__name", "id")
    if country:
        rows = rows.filter(country_id=country)
    if province:
        rows = rows.filter(province_id=province)
    if after:
        rows = rows.filter(date_from__gte=after)
    if before:
        rows = rows.filter(date_from__lte=before)
    if flag == "jure":
        rows = rows.filter(de_jure=True, de_facto=False)
    elif flag == "facto":
        rows = rows.filter(de_facto=True, de_jure=False)
    elif flag == "both":
        rows = rows.filter(de_jure=True, de_facto=True)
    if q.strip():
        rows = rows.filter(Q(province__name__icontains=q.strip()) | Q(province__code__icontains=q.strip()))
    total = rows.count()
    return MapOwnershipPage(total=total, rows=[_ownership(o) for o in rows[max(offset, 0): max(offset, 0) + min(max(limit, 1), 500)]])


def _save_ownership(row, body):
    row.province = get_object_or_404(Province, pk=body.province)
    row.country = get_object_or_404(Country, pk=body.country)
    row.date_from, row.de_jure, row.de_facto = body.date_from, body.de_jure, body.de_facto
    territory.check_life(row.country, row.date_from)
    row.full_clean(validate_constraints=False)
    clash = Ownership.objects.filter(province=row.province, country=row.country, date_from=row.date_from).exclude(pk=row.pk)
    if clash.exists():
        raise ValidationError("Такая запись уже есть: та же провинция, страна и дата.")
    if not (row.de_jure or row.de_facto):
        raise ValidationError("Нужно отметить де-юре или де-факто.")
    row.save()
    return _ownership(row)


@router.post("/ownerships", response=MapOwnershipRow)
def create_ownership(request, body: MapOwnershipIn):
    return _save_ownership(Ownership(), body)


@router.put("/ownerships/{int:ownership_id}", response=MapOwnershipRow)
def save_ownership(request, ownership_id: int, body: MapOwnershipIn):
    return _save_ownership(get_object_or_404(Ownership, pk=ownership_id), body)


@router.delete("/ownerships/{int:ownership_id}")
def delete_ownership(request, ownership_id: int):
    get_object_or_404(Ownership, pk=ownership_id).delete()
    return {}


@router.post("/ownerships/delete", response=dict[str, int])
def delete_ownerships(request, body: MapIds):
    deleted, _ = Ownership.objects.filter(pk__in=body.ids).delete()
    return {"deleted": deleted}


# ---------- правка территорий на дату ----------

class MapOwnerOnDate(Schema):
    country: int
    color: str
    de_jure: bool
    de_facto: bool


class MapApplyIn(Schema):
    codes: list[str]
    country: int
    date: dt.date
    de_jure: bool = True
    de_facto: bool = True


class MapEraseIn(Schema):
    codes: list[str]
    date: dt.date


class MapTransferIn(Schema):
    source: int
    target: int
    date: dt.date
    de_jure: bool = True
    de_facto: bool = True


class MapApplyOut(Schema):
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    later: int = 0
    moved: int = 0
    missing: list[str] = []


class MapEraseOut(Schema):
    deleted: int
    none: int


@router.get("/territory/owners", response=dict[str, MapOwnerOnDate])
def owners(request, date: dt.date | None = None):
    """Кто чем владеет на дату: по коду провинции из тайлов, для раскраски карты."""
    return territory.owners_on(date)


@router.get("/territory/dates", response=list[dt.date])
def dates(request):
    """Даты, в которые менялись границы."""
    return list(Ownership.objects.order_by("date_from").values_list("date_from", flat=True).distinct())


@router.get("/territory/country/{int:country_id}", response=list[str])
def country_provinces(request, country_id: int, date: dt.date | None = None):
    return territory.provinces_of(get_object_or_404(Country, pk=country_id), date)


@router.post("/territory/apply", response=MapApplyOut)
def apply(request, body: MapApplyIn):
    return territory.apply_ownership(body.codes, get_object_or_404(Country, pk=body.country), body.date, body.de_jure, body.de_facto)


@router.post("/territory/erase", response=MapEraseOut)
def erase(request, body: MapEraseIn):
    return territory.erase_ownership(body.codes, body.date)


@router.post("/territory/transfer", response=MapApplyOut)
def transfer(request, body: MapTransferIn):
    return territory.transfer_country(
        get_object_or_404(Country, pk=body.source), get_object_or_404(Country, pk=body.target), body.date, body.de_jure, body.de_facto
    )


# ---------- проверка данных ----------

class MapCheckItem(Schema):
    kind: str
    id: int
    label: str


class MapCheck(Schema):
    code: str
    level: str
    title: str
    count: int
    items: list[MapCheckItem]


@router.get("/checks", response=list[MapCheck])
def checks(request):
    return territory.checks()
