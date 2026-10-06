import json
from datetime import date

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.urls import path

from .models import Country, CountryLabel, Ownership, Province
from .views import _latest_ownerships

APPLY_MAX_PROVINCES = 10000


class CountryLabelInline(admin.TabularInline):
    model = CountryLabel
    extra = 0
    fields = ("text", "lng", "lat", "rank")
    show_change_link = True  # ссылка на страницу подписи, где точка ставится на карте


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    inlines = (CountryLabelInline,)
    list_display = ("name", "code", "valid_from", "valid_to", "predecessor")
    search_fields = ("name", "code")
    list_filter = ("valid_from",)
    autocomplete_fields = ("predecessor",)


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "source_code")
    search_fields = ("name", "code", "source_code")


@admin.register(Ownership)
class OwnershipAdmin(admin.ModelAdmin):
    list_display = ("province", "country", "date_from", "de_jure", "de_facto")
    list_filter = ("de_jure", "de_facto", "country")
    search_fields = ("province__name", "province__code", "country__name", "country__code")
    autocomplete_fields = ("province", "country")
    date_hierarchy = "date_from"

    # Кнопка «Редактор территорий» на странице списка владений
    change_list_template = "admin/map/ownership/change_list.html"

    def get_urls(self):
        # свои адреса должны идти раньше стандартных (иначе editor/ примется за id записи)
        custom = [
            path("editor/", self.admin_site.admin_view(self.editor_view),
                 name="map_ownership_editor"),
            path("editor/country-provinces/", self.admin_site.admin_view(self.country_provinces_view),
                 name="map_ownership_country_provinces"),
            path("editor/province/", self.admin_site.admin_view(self.province_info_view),
                 name="map_ownership_province_info"),
            path("editor/apply/", self.admin_site.admin_view(self.apply_view),
                 name="map_ownership_apply"),
        ]
        return custom + super().get_urls()

    def editor_view(self, request):
        """Страница редактора: карта слева, панель выделения и инспектор справа."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        context = {
            **self.admin_site.each_context(request),
            "title": "Редактор территорий",
            "opts": self.model._meta,
            "countries": Country.objects.order_by("name", "code"),
            # кнопка передачи показывается только тем, кто может создавать и менять владения
            "can_apply": self.has_add_permission(request) and self.has_change_permission(request),
        }
        return TemplateResponse(request, "admin/map/ownership/editor.html", context)

    def country_provinces_view(self, request):
        """Коды провинций (adm1_code), которые на дату принадлежат стране. Только чтение."""
        if not self.has_view_permission(request):
            raise PermissionDenied

        qs, error = _latest_ownerships(request)
        if error:
            return error

        try:
            country_id = int(request.GET.get("country", ""))
        except ValueError:
            return JsonResponse({"error": "country is required"}, status=400)

        # владелец «на дату» определяется по последней записи каждой провинции,
        # поэтому по стране фильтруем уже после выбора последних записей
        rows = qs.values_list("province__source_code", "country_id")
        return JsonResponse({"codes": [code for code, cid in rows if cid == country_id]})

    def province_info_view(self, request):
        """Данные провинции для инспектора: владелец на дату и вся история. Только чтение."""
        if not self.has_view_permission(request):
            raise PermissionDenied

        on_date = None
        raw = request.GET.get("date")
        if raw:
            try:
                on_date = date.fromisoformat(raw)
            except ValueError:
                return JsonResponse({"error": "date must be YYYY-MM-DD"}, status=400)

        province = Province.objects.filter(source_code=request.GET.get("source_code", "")).first()
        if province is None:
            return JsonResponse({"error": "province not found"}, status=404)

        rows = list(
            Ownership.objects.filter(province=province)
            .select_related("country")
            .order_by("-date_from", "-id")
        )
        # записи отсортированы от новых к старым: первая запись не позже даты и есть владелец
        current = next((o for o in rows if on_date is None or o.date_from <= on_date), None)

        history = [
            {
                "date_from": o.date_from.isoformat(),
                "country_id": o.country_id,
                "country": o.country.name,
                "country_code": o.country.code,
                "color": o.country.color,
                "de_jure": o.de_jure,
                "de_facto": o.de_facto,
                "current": o is current,
            }
            for o in rows
        ]
        owner = None
        if current is not None:
            owner = {
                "id": current.country_id,
                "name": current.country.name,
                "code": current.country.code,
                "color": current.country.color,
            }

        return JsonResponse({
            "source_code": province.source_code,
            "code": province.code,
            "name": province.name,
            "wiki_url": province.wiki_url,
            "owner": owner,
            "history": history,
        })

    def apply_view(self, request):
        """Передача выделенных провинций стране с даты.

        POST JSON: {"codes": [adm1_code, ...], "country": id, "date": "YYYY-MM-DD",
                    "de_jure": bool, "de_facto": bool}

        Для каждой провинции:
        - есть запись ровно на эту дату: она обновляется (страна и права);
        - иначе, если на эту дату владение уже точно такое же, ничего не делается;
        - иначе создаётся новая запись с этой датой.
        Более поздние записи не трогаются и продолжают действовать со своих дат.
        Всё выполняется одной транзакцией: при ошибке не меняется ничего.
        """
        if request.method != "POST":
            return JsonResponse({"error": "нужен POST"}, status=405)
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
            raise PermissionDenied

        try:
            payload = json.loads(request.body or b"{}")
            codes = payload["codes"]
            country_id = int(payload["country"])
            on_date = date.fromisoformat(payload["date"])
            de_jure = bool(payload.get("de_jure", True))
            de_facto = bool(payload.get("de_facto", True))
        except (ValueError, KeyError, TypeError):
            return JsonResponse({"error": "неверный запрос"}, status=400)

        if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
            return JsonResponse({"error": "codes должен быть списком строк"}, status=400)
        codes = list(dict.fromkeys(codes))  # без повторов, порядок сохраняется
        if not codes:
            return JsonResponse({"error": "ничего не выделено"}, status=400)
        if len(codes) > APPLY_MAX_PROVINCES:
            return JsonResponse(
                {"error": f"слишком много провинций (максимум {APPLY_MAX_PROVINCES})"}, status=400
            )
        if not (de_jure or de_facto):
            return JsonResponse({"error": "нужно выбрать de jure или de facto"}, status=400)

        country = Country.objects.filter(pk=country_id).first()
        if country is None:
            return JsonResponse({"error": "страна не найдена"}, status=404)
        if on_date < country.valid_from or (country.valid_to and on_date > country.valid_to):
            period = f"{country.valid_from} - {country.valid_to or '...'}"
            return JsonResponse(
                {"error": f"страна {country.code} существует {period}, дата {on_date} вне этого периода"},
                status=400,
            )

        provinces = {p.source_code: p for p in Province.objects.filter(source_code__in=codes)}
        missing = [c for c in codes if c not in provinces]

        # история владений выбранных провинций: от новых записей к старым
        by_province = {}
        for o in Ownership.objects.filter(province__in=provinces.values()).order_by(
            "province_id", "-date_from", "-id"
        ):
            by_province.setdefault(o.province_id, []).append(o)

        wanted = (country.pk, de_jure, de_facto)
        to_create, to_update = [], []
        unchanged = later = 0

        for province in provinces.values():
            rows = by_province.get(province.pk, [])
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
                unchanged += 1  # на эту дату владение и так такое
            else:
                to_create.append(Ownership(
                    province=province, country=country, date_from=on_date,
                    de_jure=de_jure, de_facto=de_facto,
                ))

        with transaction.atomic():
            Ownership.objects.bulk_create(to_create)
            Ownership.objects.bulk_update(to_update, ["country", "de_jure", "de_facto"])

        return JsonResponse({
            "created": len(to_create),
            "updated": len(to_update),
            "unchanged": unchanged,
            "later": later,
            "missing": missing,
        })


@admin.register(CountryLabel)
class CountryLabelAdmin(admin.ModelAdmin):
    list_display = ("label_text", "country", "rank", "lng", "lat")
    list_filter = ("rank",)
    list_select_related = ("country",)
    search_fields = ("text", "country__name", "country__code")
    autocomplete_fields = ("country",)
    fields = ("country", "text", "rank", "lng", "lat")
    # шаблон со встроенной картой для выбора точки
    change_form_template = "admin/map/countrylabel/change_form.html"

    @admin.display(description="Текст")
    def label_text(self, obj):
        return obj.display_text