from django.shortcuts import render
from django.http import JsonResponse
from .models import Ownership

def index(request):
    return render(request, 'map.html')

def province_colors(request):
    rows = (
        Ownership.objects
        .order_by("province_id", "-date_from", "-id")
        .distinct("province_id")
        .values_list("province__source_code", "province__code", "country__color")
    )
    return JsonResponse(
        {source_code: {"code": code, "color": color} for source_code, code, color in rows}
    )