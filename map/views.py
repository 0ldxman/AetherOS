from datetime import date

from django.http import JsonResponse
from django.shortcuts import render

from .models import CountryLabel, Ownership


def index(request):
    return render(request, 'map.html')


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


def province_colors(request):
    qs, error = _latest_ownerships(request)
    if error:
        return error

    rows = qs.values_list("province__source_code", "province__code", "country__color")
    return JsonResponse(
        {source_code: {"code": code, "color": color} for source_code, code, color in rows}
    )


def country_labels(request):
    """Подписи стран, которым на выбранную дату принадлежит хотя бы одна провинция."""
    qs, error = _latest_ownerships(request)
    if error:
        return error

    country_ids = set(qs.values_list("country_id", flat=True))
    labels = CountryLabel.objects.filter(country_id__in=country_ids).select_related("country")

    return JsonResponse(
        [
            {"text": label.display_text, "lng": label.lng, "lat": label.lat, "rank": label.rank}
            for label in labels
        ],
        safe=False,
    )


def timeline_dates(request):
    """Даты, в которые менялись границы: из них строятся засечки таймлайна."""
    days = Ownership.objects.order_by("date_from").values_list("date_from", flat=True).distinct()
    return JsonResponse({"dates": [d.isoformat() for d in days]})