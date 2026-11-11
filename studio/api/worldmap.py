"""Карта: страны и их подписи, провинции, владения, правка территорий на дату и проверка данных.

Логика правки владений живёт в map.territory (её же зовёт старая админка), здесь только схемы и коды ответов.
Сцены карты лежат в studio/api/mapscenes.py.
"""
import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Exists, F, Max, OuterRef, ProtectedError, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from map import territory
from map.bounds import bounds_of
from map.models import Country, CountryLabel, Ownership, Province

router = Router(tags=["map"])

COUNTRY_FIELDS = ("code", "name", "color", "valid_from", "valid_to", "wiki_url", "show_info")
PAGE = 100


class MapMaterial(Schema):
    """Объект, привязанный к стране или провинции: что игрок откроет из карточки на карте."""
    id: int
    slug: str
    name: str
    format: str
    where: list[str]          # «диск:/путь» мест, где объект лежит; пусто: игрок его не откроет


def _material(item):
    if item is None:
        return None
    return MapMaterial(id=item.pk, slug=item.slug, name=item.name, format=item.format, where=[str(p) for p in list(item.placements.all())[:6]])


def _item_or_error(pk):
    from filesystem.models import Item

    if not pk:
        return None
    item = Item.objects.filter(pk=pk).first()
    if item is None:
        raise ValidationError({"material": ["Такого объекта нет."]})
    return item


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
    show_info: bool
    material: int | None
    material_info: MapMaterial | None
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
    show_info: bool = True
    material: int | None = None


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
        **_row(country, _now(), None), wiki_url=country.wiki_url, show_info=country.show_info, material=country.material_id, material_info=_material(country.material),
        successors=[name for name, _ in successors], successor_ids=[pk for _, pk in successors],
        label_list=[_label(label) for label in country.labels.select_related("country")],
    )


def _save_country(country, body):
    for name in COUNTRY_FIELDS:
        setattr(country, name, getattr(body, name))
    country.predecessor = Country.objects.filter(pk=body.predecessor).first() if body.predecessor else None
    country.material = _item_or_error(body.material)
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


class MapChange(Schema):
    """Последняя смена владельца провинции: кто был (пусто у первой записи), кто стал, с какой даты и по какому праву."""
    date: dt.date
    old: str | None
    old_color: str | None
    new: str
    new_color: str
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
    last_change: MapChange | None = None


class MapProvincePage(Schema):
    total: int
    rows: list[MapProvinceRow]


class MapProvinceIn(Schema):
    code: str
    source_code: str
    name: str
    wiki_url: str = ""
    show_info: bool = True
    material: int | None = None


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
    show_info: bool
    material: int | None
    material_info: MapMaterial | None
    history: list[MapHistoryRow]


def _owner(o):
    if o is None:
        return None
    return MapOwnerRef(country=o.country_id, country_name=o.country.name, color=o.country.color, since=o.date_from, de_jure=o.de_jure, de_facto=o.de_facto)


PROVINCE_SORTS = {"name": ("name", "id"), "code": ("code",), "records": ("records", "name"), "last": ("last_date", "name")}


def _last_changes(ids, on):
    """Последняя смена владельца для каждой провинции из ids (на дату on, без даты: самая свежая)."""
    qs = Ownership.objects.filter(province_id__in=ids).select_related("country")
    if on is not None:
        qs = qs.filter(date_from__lte=on)
    rows = {}
    for o in qs.order_by("province_id", "-date_from", "-id"):
        rows.setdefault(o.province_id, []).append(o)
    out = {}
    for pid, chain in rows.items():
        last, before = chain[0], (chain[1] if len(chain) > 1 else None)
        out[pid] = MapChange(
            date=last.date_from, old=before.country.name if before else None, old_color=before.country.color if before else None,
            new=last.country.name, new_color=last.country.color, de_jure=last.de_jure, de_facto=last.de_facto,
        )
    return out


@router.get("/provinces", response=MapProvincePage)
def provinces(request, q: str = "", owner: str = "", on: dt.date | None = None, offset: int = 0, limit: int = PAGE, sort: str = "name"):
    """owner: id страны или none (без владельца); on: на какую дату считать владельца; sort: name, code, records, last (со знаком «-» по убыванию)."""
    rows = Province.objects.annotate(records=Count("ownerships", distinct=True), last_date=Max("ownerships__date_from"))
    fields = PROVINCE_SORTS.get(sort.lstrip("-"), PROVINCE_SORTS["name"])
    rows = rows.order_by(*[("-" + f if sort.startswith("-") else f) for f in fields], "id")
    if q.strip():
        rows = rows.filter(Q(name__icontains=q.strip()) | Q(code__icontains=q.strip()) | Q(source_code__icontains=q.strip()))
    now = territory.latest(on)
    if owner == "none":
        rows = rows.exclude(pk__in=list(now))
    elif owner.isdigit():
        rows = rows.filter(pk__in=[pid for pid, o in now.items() if o.country_id == int(owner)])
    total = rows.count()
    page = list(rows[max(offset, 0): max(offset, 0) + min(max(limit, 1), 500)])
    changes = _last_changes([p.pk for p in page], on)
    return MapProvincePage(total=total, rows=[
        MapProvinceRow(id=p.pk, bounds=bounds_of(p.source_code), code=p.code, source_code=p.source_code, name=p.name, wiki_url=p.wiki_url, owner=_owner(now.get(p.pk)),
                       records=p.records, last_change=changes.get(p.pk))
        for p in page
    ])


def _province_out(province, on):
    info = territory.province_info(province, on)
    now = info["owner"]
    return MapProvinceOut(
        id=province.pk, bounds=bounds_of(province.source_code), code=province.code, source_code=province.source_code, name=province.name, wiki_url=province.wiki_url,
        owner=_owner(now), records=len(info["history"]), show_info=province.show_info, material=province.material_id, material_info=_material(province.material),
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
    for name in ("code", "source_code", "name", "wiki_url", "show_info"):
        setattr(province, name, getattr(body, name))
    province.material = _item_or_error(body.material)
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

class MapPrev(Schema):
    """Прежний владелец провинции перед этой записью."""
    country: int
    country_name: str
    country_code: str
    color: str


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
    previous: MapPrev | None = None
    problem: str = ""        # early (до рождения страны), late (после распада), dup (две записи на одну дату), пусто: всё в порядке


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


def _prev_of(o):
    if o is None:
        return None
    return MapPrev(country=o.country_id, country_name=o.country.name, country_code=o.country.code, color=o.country.color)


def _ownership(o, previous=None, problem=""):
    return MapOwnershipRow(
        id=o.pk, province=o.province_id, province_name=o.province.name, province_code=o.province.code, country=o.country_id,
        country_name=o.country.name, country_code=o.country.code, color=o.country.color, date_from=o.date_from, de_jure=o.de_jure, de_facto=o.de_facto,
        previous=_prev_of(previous), problem=problem,
    )


def _previous_records(province_ids=None):
    """{id записи: прежняя запись той же провинции с более ранней датой или None}. Без списка провинций: по всему миру."""
    qs = Ownership.objects.select_related("country").order_by("province_id", "date_from", "id")
    if province_ids is not None:
        qs = qs.filter(province_id__in=province_ids)
    chains = {}
    for o in qs:
        chains.setdefault(o.province_id, []).append(o)
    found = {}
    for chain in chains.values():
        earlier = None
        index = 0
        for o in chain:
            while index < len(chain) and chain[index].date_from < o.date_from:
                earlier = chain[index]
                index += 1
            found[o.pk] = earlier
    return found


def _problems_of(rows):
    """{id записи: early | late | dup} для записей на странице."""
    pairs = {(o.province_id, o.date_from) for o in rows}
    dup = set()
    if pairs:
        for row in Ownership.objects.filter(province_id__in={p for p, _ in pairs}).values("province_id", "date_from").annotate(n=Count("id")).filter(n__gt=1):
            dup.add((row["province_id"], row["date_from"]))
    out = {}
    for o in rows:
        c = o.country
        if o.date_from < c.valid_from:
            out[o.pk] = "early"
        elif c.valid_to and o.date_from > c.valid_to:
            out[o.pk] = "late"
        elif (o.province_id, o.date_from) in dup:
            out[o.pk] = "dup"
    return out


def _filtered_ownerships(q="", country=None, role="to", province=None, after=None, before=None, flag="", problem=""):
    rows = Ownership.objects.select_related("province", "country")
    if country:
        if role == "from":
            ids = [pk for pk, prev in _previous_records().items() if prev is not None and prev.country_id == country]
            rows = rows.filter(pk__in=ids)
        else:
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
        word = q.strip()
        rows = rows.filter(Q(province__name__icontains=word) | Q(province__code__icontains=word) | Q(country__name__icontains=word) | Q(country__code__icontains=word))
    if problem == "early":
        rows = rows.filter(date_from__lt=F("country__valid_from"))
    elif problem == "late":
        rows = rows.filter(country__valid_to__isnull=False, date_from__gt=F("country__valid_to"))
    elif problem == "dup":
        rows = rows.filter(Exists(Ownership.objects.filter(province_id=OuterRef("province_id"), date_from=OuterRef("date_from")).exclude(pk=OuterRef("pk"))))
    return rows


@router.get("/ownerships", response=MapOwnershipPage)
def ownerships(request, q: str = "", country: int | None = None, role: str = "to", province: int | None = None, after: dt.date | None = None,
               before: dt.date | None = None, flag: str = "", problem: str = "", sort: str = "-date", offset: int = 0, limit: int = PAGE):
    """flag: jure | facto | both. role: to (страна получила) или from (страна отдала). problem: early | late | dup. sort: date | -date | province."""
    rows = _filtered_ownerships(q, country, role, province, after, before, flag, problem)
    order = {"date": ("date_from", "province__name", "id"), "province": ("province__name", "-date_from", "id")}.get(sort, ("-date_from", "province__name", "id"))
    rows = rows.order_by(*order)
    total = rows.count()
    page = list(rows[max(offset, 0): max(offset, 0) + min(max(limit, 1), 500)])
    prev = _previous_records({o.province_id for o in page})
    problems = _problems_of(page)
    return MapOwnershipPage(total=total, rows=[_ownership(o, prev.get(o.pk), problems.get(o.pk, "")) for o in page])


class MapProblemCounts(Schema):
    early: int
    late: int
    dup: int


@router.get("/ownerships/problems", response=MapProblemCounts)
def ownership_problems(request):
    return MapProblemCounts(
        early=_filtered_ownerships(problem="early").count(), late=_filtered_ownerships(problem="late").count(), dup=_filtered_ownerships(problem="dup").count(),
    )


# ---------- события: записи одной даты и одной страны-получателя ----------

class MapEventFrom(Schema):
    name: str
    color: str
    count: int


class MapEvent(Schema):
    date: dt.date
    country: int
    country_name: str
    country_code: str
    color: str
    count: int
    jure: int                 # у скольких записей события есть де-юре
    facto: int                # и де-факто (права у записей одного события могут быть разными)
    froms: list[MapEventFrom]  # от кого перешли провинции (самые крупные первыми)
    fresh: int                # записей без прежнего владельца


class MapEventPage(Schema):
    total: int                # событий
    records: int              # записей в них
    rows: list[MapEvent]


@router.get("/ownerships/events", response=MapEventPage)
def ownership_events(request, q: str = "", country: int | None = None, role: str = "to", after: dt.date | None = None, before: dt.date | None = None,
                     flag: str = "", problem: str = "", sort: str = "-date", offset: int = 0, limit: int = PAGE):
    """События: записи сгруппированы по дате и стране-получателю (права внутри события могут различаться)."""
    base = _filtered_ownerships(q, country, role, None, after, before, flag, problem)
    groups = base.order_by().values("date_from", "country_id").annotate(
        count=Count("id"), jure=Count("id", filter=Q(de_jure=True)), facto=Count("id", filter=Q(de_facto=True)),
    )
    order = {"date": ("date_from", "country__name"), "count": ("count", "-date_from"), "-count": ("-count", "-date_from")}.get(sort, ("-date_from", "country__name"))
    groups = groups.order_by(*order)
    total = groups.count()
    page = list(groups[max(offset, 0): max(offset, 0) + min(max(limit, 1), 500)])
    countries = {c.pk: c for c in Country.objects.filter(pk__in={g["country_id"] for g in page})}
    members = {}
    if page:
        wanted = Q()
        for g in page:
            wanted |= Q(date_from=g["date_from"], country_id=g["country_id"])
        records = list(base.filter(wanted))
        prev = _previous_records({o.province_id for o in records})
        for o in records:
            members.setdefault((o.date_from, o.country_id), []).append(prev.get(o.pk))
    out = []
    for g in page:
        c = countries[g["country_id"]]
        counted = {}
        fresh = 0
        for before_owner in members.get((g["date_from"], g["country_id"]), []):
            if before_owner is None:
                fresh += 1
            else:
                key = before_owner.country_id
                name, color, n = counted.get(key, (before_owner.country.name, before_owner.country.color, 0))
                counted[key] = (name, color, n + 1)
        froms = [MapEventFrom(name=n, color=col, count=k) for n, col, k in sorted(counted.values(), key=lambda item: -item[2])]
        out.append(MapEvent(date=g["date_from"], country=c.pk, country_name=c.name, country_code=c.code, color=c.color, count=g["count"],
                            jure=g["jure"], facto=g["facto"], froms=froms, fresh=fresh))
    return MapEventPage(total=total, records=base.count(), rows=out)


# ---------- пачки: смена даты и прав, удаление ----------

class MapEventKey(Schema):
    date: dt.date
    country: int


class MapBulkIn(Schema):
    ids: list[int] = []
    events: list[MapEventKey] = []
    action: str                          # update | delete
    date: dt.date | None = None          # новая дата
    shift_days: int | None = None        # или сдвиг на столько дней (может быть отрицательным)
    de_jure: bool | None = None          # новые права (None: не менять)
    de_facto: bool | None = None
    dry_run: bool = False                # только посчитать, ничего не менять


class MapBulkOut(Schema):
    matched: int
    changed: int
    deleted: int
    conflicts: int
    examples: list[str]                  # первые несколько причин, почему запись пропущена


@router.post("/ownerships/bulk", response=MapBulkOut)
def ownerships_bulk(request, body: MapBulkIn):
    import datetime as _dt

    wanted = Q(pk__in=body.ids)
    for event in body.events:
        wanted |= Q(date_from=event.date, country_id=event.country)
    rows = list(Ownership.objects.filter(wanted).select_related("province", "country")) if (body.ids or body.events) else []
    if body.action == "delete":
        deleted = 0
        if rows and not body.dry_run:
            with transaction.atomic():
                deleted, _ = Ownership.objects.filter(pk__in=[o.pk for o in rows]).delete()
        return MapBulkOut(matched=len(rows), changed=0, deleted=deleted if not body.dry_run else len(rows), conflicts=0, examples=[])
    if body.action != "update":
        raise ValidationError("Действие: update или delete.")
    if body.date is None and not body.shift_days and body.de_jure is None and body.de_facto is None:
        raise ValidationError("Укажите новую дату, сдвиг или права.")
    moving = {o.pk for o in rows}
    taken = set(Ownership.objects.exclude(pk__in=moving).values_list("province_id", "country_id", "date_from"))
    slots, changes, examples, conflicts = set(), [], [], 0

    def skip(text):
        nonlocal conflicts
        conflicts += 1
        if len(examples) < 5:
            examples.append(text)

    for o in rows:
        new_date = body.date or (o.date_from + _dt.timedelta(days=body.shift_days or 0))
        jure = o.de_jure if body.de_jure is None else body.de_jure
        facto = o.de_facto if body.de_facto is None else body.de_facto
        if not (jure or facto):
            skip(f"{o.province.code}: нужно оставить де-юре или де-факто")
            continue
        try:
            territory.check_life(o.country, new_date)
        except territory.TerritoryError as error:
            skip(f"{o.province.code}: {error}")
            continue
        slot = (o.province_id, o.country_id, new_date)
        if slot in taken or slot in slots:
            skip(f"{o.province.code}: у провинции уже есть запись для {o.country.code} на {new_date}")
            continue
        slots.add(slot)
        if (new_date, jure, facto) != (o.date_from, o.de_jure, o.de_facto):
            o.date_from, o.de_jure, o.de_facto = new_date, jure, facto
            changes.append(o)
    if changes and not body.dry_run:
        from map.cache import bump_version

        with transaction.atomic():
            Ownership.objects.bulk_update(changes, ["date_from", "de_jure", "de_facto"])
        bump_version()
    return MapBulkOut(matched=len(rows), changed=len(changes), deleted=0, conflicts=conflicts, examples=examples)


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
