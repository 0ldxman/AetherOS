"""Сохранённые карты (сцены): список, правка, история снимков, откат, выгрузка и загрузка файла.

Пометки проверяет map.scenes.clean_features (при full_clean сцены), снимки и перенос: map.revisions. Миниатюра в Студии не
передаётся: список её не показывает, а на странице карты её снимает старый редактор.
"""
import datetime as dt

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from documents.markup.expr import SpoilerSyntaxError, parse_expr
from map.models import MapScene, MapSceneRevision
from map.revisions import apply_data, export_scenes, import_scenes, record_revision
from secure.access import format_condition

router = Router(tags=["map-scenes"])


class MapSceneRow(Schema):
    id: int
    slug: str
    title: str
    base_date: dt.date | None
    mode: str
    features: int
    keys: bool
    updated_at: dt.datetime


class MapSceneIn(Schema):
    slug: str
    title: str
    base_date: dt.date | None = None
    mode: str = "political"
    lat: float = 20
    lon: float = 10
    zoom: float = 3
    bounds: list[float] | None = None
    min_zoom: float | None = None
    max_zoom: float | None = None
    flat: bool = False
    features: list[dict] = []
    keys: str = ""


class MapSceneOut(MapSceneIn):
    id: int
    updated_at: dt.datetime
    created_at: dt.datetime


class MapRevisionRow(Schema):
    id: int
    saved_at: dt.datetime
    saved_by: str
    features: int
    title: str


class MapSceneFile(Schema):
    items: list[dict]


class MapImportOut(Schema):
    created: int
    updated: int


def _out(scene):
    return MapSceneOut(
        id=scene.pk, slug=scene.slug, title=scene.title, base_date=scene.base_date, mode=scene.mode, lat=scene.lat, lon=scene.lon,
        zoom=scene.zoom, bounds=scene.bounds, min_zoom=scene.min_zoom, max_zoom=scene.max_zoom, flat=scene.flat, features=scene.features or [],
        keys=format_condition(scene.key_condition) if scene.key_condition else "", updated_at=scene.updated_at, created_at=scene.created_at,
    )


@router.get("", response=list[MapSceneRow])
def scenes(request, q: str = ""):
    rows = MapScene.objects.defer("features", "thumbnail").order_by("title")
    if q.strip():
        rows = rows.filter(Q(title__icontains=q.strip()) | Q(slug__icontains=q.strip()))
    counts = dict(MapScene.objects.values_list("id", "features"))
    return [
        MapSceneRow(id=s.pk, slug=s.slug, title=s.title, base_date=s.base_date, mode=s.mode, features=len(counts.get(s.pk) or []),
                    keys=bool(s.key_condition), updated_at=s.updated_at)
        for s in rows
    ]


def _save(scene, body, user):
    scene.slug, scene.title, scene.base_date, scene.mode = body.slug.strip(), body.title.strip(), body.base_date, body.mode
    scene.lat, scene.lon, scene.zoom, scene.bounds = body.lat, body.lon, body.zoom, body.bounds
    scene.min_zoom, scene.max_zoom, scene.flat, scene.features = body.min_zoom, body.max_zoom, body.flat, body.features
    try:
        scene.key_condition = parse_expr(body.keys) if body.keys.strip() else None
    except SpoilerSyntaxError as exc:
        raise ValidationError({"keys": [str(exc)]})
    scene.full_clean()
    scene.save()
    record_revision(scene, user)
    return _out(scene)


@router.get("/{int:scene_id}", response=MapSceneOut)
def read(request, scene_id: int):
    return _out(get_object_or_404(MapScene, pk=scene_id))


@router.post("", response=MapSceneOut)
def create(request, body: MapSceneIn):
    return _save(MapScene(), body, request.user)


@router.put("/{int:scene_id}", response=MapSceneOut)
def save(request, scene_id: int, body: MapSceneIn):
    return _save(get_object_or_404(MapScene, pk=scene_id), body, request.user)


@router.post("/{int:scene_id}/copy", response=MapSceneOut)
def copy(request, scene_id: int):
    """Копия сцены под новым слагом (-copy, -copy-2...)."""
    source = get_object_or_404(MapScene, pk=scene_id)
    slug, n = f"{source.slug}-copy"[:64], 2
    while MapScene.objects.filter(slug=slug).exists():
        slug = f"{source.slug[:56]}-copy-{n}"
        n += 1
    clone = MapScene(slug=slug, title=f"{source.title} (копия)"[:128])
    apply_data(clone, {name: getattr(source, name) for name in ("base_date", "mode", "lat", "lon", "zoom", "bounds", "min_zoom", "max_zoom", "flat", "features", "key_condition")})
    clone.full_clean()
    clone.save()
    record_revision(clone, request.user)
    return _out(clone)


@router.delete("/{int:scene_id}")
def delete(request, scene_id: int):
    get_object_or_404(MapScene, pk=scene_id).delete()
    return {}


@router.get("/{int:scene_id}/revisions", response=list[MapRevisionRow])
def revisions(request, scene_id: int):
    scene = get_object_or_404(MapScene, pk=scene_id)
    return [
        MapRevisionRow(id=r.pk, saved_at=r.saved_at, saved_by=r.saved_by.get_username() if r.saved_by_id else "", features=len(r.data.get("features") or []),
                       title=r.data.get("title", ""))
        for r in scene.revisions.select_related("saved_by")
    ]


@router.post("/{int:scene_id}/revisions/{int:revision_id}/restore", response=MapSceneOut)
def restore(request, scene_id: int, revision_id: int):
    scene = get_object_or_404(MapScene, pk=scene_id)
    revision = get_object_or_404(MapSceneRevision, pk=revision_id, scene=scene)
    apply_data(scene, revision.data)
    scene.full_clean()
    scene.save()
    record_revision(scene, request.user)
    return _out(scene)


@router.get("/export", response=MapSceneFile)
def export(request, ids: str = ""):
    """Выгрузка сцен (все или список id через запятую) списком словарей."""
    chosen = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    rows = MapScene.objects.filter(pk__in=chosen) if chosen else MapScene.objects.all()
    return MapSceneFile(items=export_scenes(rows.order_by("slug")))


@router.post("/import", response=MapImportOut)
def import_file(request, body: MapSceneFile):
    created, updated = import_scenes(body.items, request.user)
    return MapImportOut(created=created, updated=updated)
