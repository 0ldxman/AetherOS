import json
from datetime import date

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import format_html
from django.template.response import TemplateResponse
from django.urls import path

from map.bounds import lookup_regions
from map.revisions import apply_data, export_scenes, import_scenes, record_revision
from map.models import Country, CountryLabel, MapScene, MapSceneRevision, Ownership, Province
from map.views import _latest_ownerships

APPLY_MAX_PROVINCES = 10000


class CountryLabelInline(admin.TabularInline):
    model = CountryLabel
    extra = 0
    fields = ("text", "lng", "lat", "rank")
    show_change_link = True  # ссылка на страницу подписи, где точка ставится на карте


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    inlines = (CountryLabelInline,)
    list_select_related = ("predecessor",)
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
    list_select_related = ("province", "country")
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
    list_select_related = ("country",)
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

class MapSceneRevisionInline(admin.TabularInline):
    """История сохранений: только просмотр, откат отдельной кнопкой."""

    model = MapSceneRevision
    extra = 0
    can_delete = False
    max_num = 0
    fields = ("saved_at", "saved_by", "summary", "restore")
    readonly_fields = fields
    verbose_name_plural = "История сохранений"

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Что внутри")
    def summary(self, revision):
        data = revision.data
        return f"{len(data.get('features') or [])} пометок, {data.get('title', '')}"

    @admin.display(description="")
    def restore(self, revision):
        if not revision.pk:
            return ""
        url = reverse("admin:map_mapscene_revert", args=[revision.scene_id, revision.pk])
        return format_html('<a href="{}">Восстановить</a>', url)


@admin.register(MapScene)
class MapSceneAdmin(admin.ModelAdmin):
    save_as = True          # «Сохранить как новый»: копия сцены под другим слагом
    inlines = (MapSceneRevisionInline,)
    change_list_template = "admin/map/mapscene/change_list.html"
    actions = ("export_json",)

    # рисование пометок: карта в iframe рядом с формой (map/templates/admin/map/mapscene/change_form.html)
    change_form_template = "admin/map/mapscene/change_form.html"

    list_display = ("preview", "title", "slug", "base_date", "mode", "flat", "updated_at")
    list_display_links = ("preview", "title")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("title", "slug", "base_date", "mode", "key_condition", "thumbnail")}),
        ("Камера", {"fields": ("lat", "lon", "zoom", "flat", "bounds", "min_zoom", "max_zoom")}),
        ("Пометки (JSON; рисуются в редакторе ниже)", {"fields": ("features",), "classes": ("collapse",)}),
    )

    def render_change_form(self, request, context, *args, **kwargs):
        from secure.keys import key_rows

        from map.scenes import COLORS

        from map.icons import MARKER_ICONS

        context["marker_icons"] = MARKER_ICONS
        context["colors"] = COLORS
        keys = key_rows()
        context["keys"] = [k["slug"] for k in keys]
        context["keys_info"] = keys
        return super().render_change_form(request, context, *args, **kwargs)

    @admin.display(description="Вид")
    def preview(self, scene):
        if not scene.thumbnail:
            return "—"
        return format_html('<img src="{}" alt="" style="height:64px;width:auto;border:1px solid #ccc">', scene.thumbnail)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        record_revision(obj, request.user)

    @admin.action(description="Выгрузить выбранные в JSON")
    def export_json(self, request, queryset):
        response = HttpResponse(
            json.dumps(export_scenes(queryset), ensure_ascii=False, indent=1),
            content_type="application/json; charset=utf-8",
        )
        response["Content-Disposition"] = 'attachment; filename="map-scenes.json"'
        return response

    def get_urls(self):
        # свои адреса должны идти раньше стандартных (иначе lookup/ примется за id записи)
        custom = [
            path("lookup/", self.admin_site.admin_view(self.lookup_view), name="map_mapscene_lookup"),
            path("import/", self.admin_site.admin_view(self.import_view), name="map_mapscene_import"),
            path("find/", self.admin_site.admin_view(self.find_view), name="map_mapscene_find"),
            path("<int:scene_id>/revert/<int:revision_id>/", self.admin_site.admin_view(self.revert_view),
                 name="map_mapscene_revert"),
        ]
        return custom + super().get_urls()

    def find_view(self, request):
        """Поиск сохранённых карт по названию или слагу для кнопки «+ Карта» в редакторе вики."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        query = request.GET.get("q", "").strip()
        scenes = MapScene.objects.all()
        if query:
            from django.db.models import Q

            scenes = scenes.filter(Q(title__icontains=query) | Q(slug__icontains=query))
        return JsonResponse({"items": [{"slug": s.slug, "title": s.title} for s in scenes[:30]]})

    def revert_view(self, request, scene_id, revision_id):
        """Откат к снимку: подтверждение и запись нового снимка (история не стирается)."""
        scene = get_object_or_404(MapScene, pk=scene_id)
        revision = get_object_or_404(MapSceneRevision, pk=revision_id, scene=scene)
        if not self.has_change_permission(request, scene):
            raise PermissionDenied
        change_url = reverse("admin:map_mapscene_change", args=[scene.pk])
        if request.method == "POST":
            try:
                apply_data(scene, revision.data)
                scene.full_clean()
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages))
                return redirect(change_url)
            scene.save()
            record_revision(scene, request.user)
            messages.success(request, "Карта восстановлена из снимка.")
            return redirect(change_url)
        context = {
            **self.admin_site.each_context(request), "title": "Восстановить карту", "opts": self.model._meta,
            "scene": scene, "revision": revision, "features": len(revision.data.get("features") or []),
            "change_url": change_url,
        }
        return TemplateResponse(request, "admin/map/mapscene/revert.html", context)

    def import_view(self, request):
        """Загрузка сцен из файла выгрузки: создаёт новые и обновляет существующие по слагу."""
        if not self.has_add_permission(request):
            raise PermissionDenied
        error = ""
        if request.method == "POST":
            upload = request.FILES.get("file")
            raw = upload.read().decode("utf-8") if upload else request.POST.get("text", "")
            try:
                created, updated = import_scenes(json.loads(raw or "null"), request.user)
            except (ValueError, ValidationError) as exc:
                error = "; ".join(exc.messages) if isinstance(exc, ValidationError) else f"Не разобрать JSON: {exc}"
            else:
                messages.success(request, f"Создано: {created}, обновлено: {updated}.")
                return redirect(reverse("admin:map_mapscene_changelist"))
        context = {**self.admin_site.each_context(request), "title": "Загрузить карты из JSON",
                   "opts": self.model._meta, "error": error}
        return TemplateResponse(request, "admin/map/mapscene/import.html", context)

    def lookup_view(self, request):
        """Поиск провинций и стран по названию или коду: [{kind, token, name, bounds}]."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        return JsonResponse({"results": lookup_regions(request.GET.get("q", ""))})
