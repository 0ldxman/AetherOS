from datetime import date

from django.http import Http404, JsonResponse
from django.shortcuts import render

from .cache import shared_json as _shared_json
from .models import CountryLabel, Ownership


def index(request):
    from .icons import MARKER_ICONS

    return render(request, 'map.html', {"marker_icons": MARKER_ICONS})


def _latest_ownerships(request):
    """Последнее владение каждой провинции на дату из ?date=YYYY-MM-DD
    (без параметра - самое свежее). Возвращает (queryset, None)
    или (None, ответ с ошибкой 400)."""
    qs = Ownership.objects.all()

    raw = request.GET.get("date")
    if raw:
        try:
            on_date = date.fromisoformat(raw)
        except ValueError:
            return None, JsonResponse({"error": "date must be YYYY-MM-DD"}, status=400)
        qs = qs.filter(date_from__lte=on_date)

    qs = qs.order_by("province_id", "-date_from", "-id").distinct("province_id")
    return qs, None


def link_of(province_url, country_url):
    """Ссылка по клику на провинцию: её страница, а без неё страница страны. Только http(s) и пути сайта."""
    for raw in (province_url, country_url):
        raw = (raw or "").strip()
        if raw.startswith(("http://", "https://")) or (raw.startswith("/") and not raw.startswith("//")):
            return raw
    return ""


def province_colors(request):
    qs, error = _latest_ownerships(request)
    if error:
        return error

    def compute():
        rows = qs.values_list(
            "province__source_code", "province__code", "country__color", "province__wiki_url", "country__wiki_url"
        )
        return {
            source_code: {"code": code, "color": color, "url": link_of(province_url, country_url)}
            for source_code, code, color, province_url, country_url in rows
        }

    return _shared_json("colors", request.GET.get("date", ""), compute)


def country_labels(request):
    """Подписи стран, которым на выбранную дату принадлежит хотя бы одна провинция."""
    qs, error = _latest_ownerships(request)
    if error:
        return error

    def compute():
        country_ids = set(qs.values_list("country_id", flat=True))
        labels = CountryLabel.objects.filter(country_id__in=country_ids).select_related("country")
        return [
            {"text": label.display_text, "lng": label.lng, "lat": label.lat, "rank": label.rank}
            for label in labels
        ]

    return _shared_json("labels", request.GET.get("date", ""), compute)


def timeline_dates(request):
    """Даты, в которые менялись границы: из них строятся засечки таймлайна."""
    def compute():
        days = Ownership.objects.order_by("date_from").values_list("date_from", flat=True).distinct()
        return {"dates": [d.isoformat() for d in days]}

    return _shared_json("dates", "", compute)


def _visible_scenes(request, light=False):
    """Сохранённые карты, открытые игроку по ключам. light не грузит пометки и миниатюру (списку они не нужны)."""
    from secure.access import satisfied
    from wiki.access import request_keys

    from .models import MapScene

    keys = request_keys(request)
    scenes = MapScene.objects.all()
    if light:
        scenes = scenes.defer("features", "thumbnail")
    return [scene for scene in scenes if satisfied(scene.key_condition, keys)], keys


def scene_list(request):
    """Список сохранённых карт для выбора в приложении карты."""
    scenes, _keys = _visible_scenes(request, light=True)
    return JsonResponse([
        {"slug": s.slug, "title": s.title, "date": s.base_date.isoformat() if s.base_date else ""}
        for s in scenes
    ], safe=False)


def scene_detail(request, slug):
    """Сохранённая карта целиком: камера, дата и только те пометки, что видны игроку (закрытая сцена 404)."""
    from .scenes import scene_payload

    scenes, keys = _visible_scenes(request)
    scene = next((s for s in scenes if s.slug == slug), None)
    if scene is None:
        raise Http404

    raw = request.GET.get("date")
    try:
        on_date = date.fromisoformat(raw) if raw else scene.base_date
    except ValueError:
        return JsonResponse({"error": "date must be YYYY-MM-DD"}, status=400)

    return JsonResponse({
        "slug": scene.slug,
        "title": scene.title,
        "date": scene.base_date.isoformat() if scene.base_date else "",
        "mode": scene.mode,
        "lat": scene.lat,
        "lon": scene.lon,
        "zoom": scene.zoom,
        "flat": scene.flat,
        "bounds": scene.bounds,
        "min_zoom": scene.min_zoom,
        "max_zoom": scene.max_zoom,
        "features": scene_payload(scene, keys, on_date),
    })


def resolve_regions(request):
    """Для редактора сцен: какие провинции (adm1_code) выделяет каждый токен на дату (страна по владению на дату)."""
    from .bounds import resolve_highlight

    if not getattr(request.user, "is_staff", False):
        raise Http404
    raw = request.GET.get("date")
    try:
        on_date = date.fromisoformat(raw) if raw else None
    except ValueError:
        return JsonResponse({"error": "date must be YYYY-MM-DD"}, status=400)

    result = {}
    for token in [t for t in request.GET.get("tokens", "").split(",") if t.strip()][:40]:
        groups, _unknown = resolve_highlight([token], on_date)
        result[token] = [code for group in groups for code in group["codes"]]
    return JsonResponse(result)
