from datetime import date

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.urls import path

from .models import Country, CountryLabel, Ownership, Province
from .views import _latest_ownerships


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