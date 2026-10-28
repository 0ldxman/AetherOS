"""Админка томов и объектов (docs/storage-spec.md): объект, том с деревом, размещение."""
import json

from django import forms
from django.contrib import admin
from django.db.models import Count
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from secure.admin_widgets import ConditionFieldsMixin, ConditionWidget

from .admin_preview import ItemPreviewMixin
from .models import KEY_FORMAT, FileFormat, Item, ItemKey, ItemSignature, Placement, Volume
from machines.models import MachineMount


class KeyItemConditionWidget(ConditionWidget):
    """Редактор условий, где ключи это объекты формата key."""

    def get_context(self, name, value, attrs):
        keys = [{"slug": row["slug"], "description": row["name"]} for row in Item.objects.filter(format=KEY_FORMAT).order_by("slug").values("slug", "name")]
        attrs = {**(attrs or {}), "data-keys": json.dumps(keys, ensure_ascii=False)}
        return forms.Textarea.get_context(self, name, value, attrs)


class KeyConditionsMixin(ConditionFieldsMixin):
    condition_widget = KeyItemConditionWidget


# ---- объект ---------------------------------------------------------------------------------------------------------

class ItemAdminForm(forms.ModelForm):
    format = forms.ChoiceField(label="Формат", required=False, help_text="Формат решает, что вводится в содержимое.")

    class Meta:
        model = Item
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "— без формата —")]
        choices += [(found.name, f"{found.name} — {found.title}" if found.title else found.name) for found in FileFormat.objects.order_by("name")]
        self.fields["format"].choices = choices


class KeyedInline(admin.TabularInline):
    """Ключи и подписи выбираются только среди объектов формата key."""

    fk_name = "item"
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "key":
            kwargs["queryset"] = Item.objects.filter(format=KEY_FORMAT).order_by("slug")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ItemKeyInline(KeyedInline):
    model = ItemKey
    verbose_name = "внедрённый ключ"
    verbose_name_plural = "Внедрённые ключи"


class ItemSignatureInline(KeyedInline):
    model = ItemSignature
    verbose_name = "подпись"
    verbose_name_plural = "Подписи"


@admin.register(Item)
class ItemAdmin(KeyConditionsMixin, ItemPreviewMixin, admin.ModelAdmin):
    form = ItemAdminForm
    condition_fields = ("access",)
    inlines = (ItemKeyInline, ItemSignatureInline)
    list_display = ("slug", "name", "format", "content_summary", "placements_count", "updated_at")
    list_display_links = ("slug", "name")
    list_filter = ("format",)
    search_fields = ("slug", "name", "meta", "body")
    autocomplete_fields = ("asset", "scene", "message")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    fieldsets = (
        ("Основное", {"fields": ("slug", "name", "format")}),
        ("Содержимое", {"fields": ("body", "asset", "url", "scene", "message"), "description": "Что вводится, зависит от формата."}),
        ("Доступ", {"fields": ("access",)}),
        ("Слои защиты", {"fields": ("state",), "classes": ("collapse",)}),
        ("Метаданные", {"fields": ("size", "meta", "world_created_at", "world_updated_at", "world_creator"), "classes": ("collapse",)}),
        ("Админское", {"fields": ("created_at", "updated_at", "created_by", "updated_by"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_placements=Count("placements", distinct=True))

    @admin.display(description="Содержимое")
    def content_summary(self, obj):
        if obj.asset_id:
            return f"ассет: {obj.asset.name}"
        if obj.url:
            return "ссылка"
        if obj.scene_id:
            return f"сцена: {obj.scene.slug}"
        if obj.message_id:
            return "письмо"
        return f"текст, {len(obj.body)} зн." if obj.body else "пусто"

    @admin.display(description="Размещений", ordering="_placements")
    def placements_count(self, obj):
        return obj._placements

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


# ---- том ------------------------------------------------------------------------------------------------------------

class VolumeMountInline(admin.TabularInline):
    """Кто монтирует этот том."""

    model = MachineMount
    fk_name = "volume"
    extra = 0
    fields = ("machine", "volume_path", "mount_path", "mode", "order")
    autocomplete_fields = ("machine",)


@admin.register(Volume)
class VolumeAdmin(KeyConditionsMixin, admin.ModelAdmin):
    condition_fields = ("access",)
    change_form_template = "admin/filesystem/volume/change_form.html"
    inlines = (VolumeMountInline,)
    list_display = ("slug", "name", "label", "uuid", "placements_count", "mounts_count", "tree_link")
    search_fields = ("slug", "name", "label", "uuid")
    fieldsets = (
        (None, {"fields": ("slug", "name", "uuid", "label", "access")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_placements=Count("placements", distinct=True), _mounts=Count("mounts", distinct=True))

    @admin.display(description="Размещений", ordering="_placements")
    def placements_count(self, obj):
        return obj._placements

    @admin.display(description="Монтирований", ordering="_mounts")
    def mounts_count(self, obj):
        return obj._mounts

    @admin.display(description="Дерево")
    def tree_link(self, obj):
        return format_html('<a href="{}">дерево</a>', reverse("admin:filesystem_volume_tree", args=[obj.pk]))

    def get_urls(self):
        custom = [path("<int:pk>/tree/", self.admin_site.admin_view(self.tree_view), name="filesystem_volume_tree")]
        return custom + super().get_urls()

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        response = super().render_change_form(request, context, add, change, form_url, obj)
        if obj is not None:
            response.context_data["tree_url"] = reverse("admin:filesystem_volume_tree", args=[obj.pk])
        return response

    def tree_view(self, request, pk):
        volume = self.get_object(request, str(pk))
        if volume is None:
            raise Http404
        if not self.has_view_or_change_permission(request, volume):
            raise Http404
        add_url = reverse("admin:filesystem_placement_add")
        rows = tree_rows(volume)
        for row in rows:
            row["add_url"] = f"{add_url}?volume={volume.pk}&parent={row['placement'].pk}"
            row["change_url"] = reverse("admin:filesystem_placement_change", args=[row["placement"].pk])
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"Дерево тома {volume}",
            "volume": volume,
            "rows": rows,
            "root_add_url": f"{add_url}?volume={volume.pk}",
            "change_url": reverse("admin:filesystem_volume_change", args=[volume.pk]),
        }
        return TemplateResponse(request, "admin/filesystem/volume/tree.html", context)


def tree_rows(volume):
    """Размещения тома в порядке дерева: папки перед файлами, внутри по имени; у каждого глубина и путь."""
    placements = list(volume.placements.select_related("item").order_by("name"))
    children = {}
    for placement in placements:
        children.setdefault(placement.parent_id, []).append(placement)
    rows = []

    def walk(parent_id, depth, prefix):
        branch = sorted(children.get(parent_id, []), key=lambda row: (row.kind != Placement.Kind.FOLDER, row.name.casefold()))
        for placement in branch:
            here = f"{prefix}/{placement.name}" if prefix else placement.name
            rows.append({"placement": placement, "depth": depth, "path": here})
            if placement.kind == Placement.Kind.FOLDER:
                walk(placement.pk, depth + 1, here)

    walk(None, 0, "")
    return rows


# ---- размещение -----------------------------------------------------------------------------------------------------

@admin.register(Placement)
class PlacementAdmin(KeyConditionsMixin, admin.ModelAdmin):
    condition_fields = ("access",)
    list_display = ("path_display", "volume", "kind", "item", "hidden", "system", "access_mode", "state_mode")
    list_filter = ("volume", "kind", "hidden", "system", "access_mode", "state_mode")
    search_fields = ("name", "item__slug", "item__name")
    autocomplete_fields = ("item", "volume")
    list_select_related = ("volume", "item", "parent")
    fieldsets = (
        (None, {"fields": ("volume", "parent", "kind", "item", "name")}),
        ("Свойства", {"fields": ("hidden", "system")}),
        ("Доступ", {"fields": ("access_mode", "access")}),
        ("Слои защиты", {"fields": ("state_mode", "state")}),
    )

    @admin.display(description="Путь")
    def path_display(self, obj):
        return "/" + obj.path()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            folders = Placement.objects.filter(kind=Placement.Kind.FOLDER).select_related("volume").order_by("volume__slug", "name")
            volume = request.GET.get("volume")
            if volume and volume.isdigit():
                folders = folders.filter(volume_id=int(volume))
            kwargs["queryset"] = folders
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
