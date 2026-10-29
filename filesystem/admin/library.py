"""Админка томов и объектов (docs/storage-spec.md): объект, том с деревом, размещение."""
import json

from django import forms
from django.contrib import admin
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from secure.admin_widgets import ConditionFieldsMixin, ConditionWidget

from filesystem.manager import filemanager
from filesystem.admin.files import VolumeFiles
from filesystem.admin.history import ItemHistoryMixin, VersionedFormMixin
from filesystem.admin.preview import ItemPreviewMixin
from wiki.admin_dashboard import ItemDashboardMixin

from filesystem.models import KEY_FORMAT, FileFormat, Item, ItemKey, ItemMember, ItemSignature, Placement, Volume, VolumeTemplate
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

class ItemAdminForm(VersionedFormMixin):
    format = forms.ChoiceField(label="Формат", required=False, help_text="Формат решает, что вводится в содержимое.")

    class Meta:
        model = Item
        fields = "__all__"

    def clean_state(self):
        from filesystem.layers.validators import validate_state_text

        text = self.cleaned_data.get("state", "")
        validate_state_text(text)
        return text

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


class ItemMemberInline(admin.TabularInline):
    """Члены архива: если у объекта есть члены, игрок видит его архивом (pak l, pak x)."""

    model = ItemMember
    fk_name = "archive"
    extra = 0
    autocomplete_fields = ("item",)
    verbose_name = "член архива"
    verbose_name_plural = "Члены архива"


class ItemSignatureInline(KeyedInline):
    model = ItemSignature
    verbose_name = "подпись"
    verbose_name_plural = "Подписи"


@admin.register(Item)
class ItemAdmin(ItemDashboardMixin, ItemHistoryMixin, KeyConditionsMixin, ItemPreviewMixin, admin.ModelAdmin):
    form = ItemAdminForm
    condition_fields = ("access",)
    inlines = (ItemKeyInline, ItemSignatureInline, ItemMemberInline)
    list_display = ("slug", "name", "format", "content_summary", "placements_count", "editing", "updated_at")
    list_display_links = ("slug", "name")
    list_filter = ("format",)
    search_fields = ("slug", "name", "meta", "body")
    autocomplete_fields = ("asset", "scene", "message")
    list_select_related = ("asset", "scene", "message", "lock__user")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    fieldsets = (
        ("Основное", {"fields": ("slug", "name", "format", "base_version")}),
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


class VolumeForm(forms.ModelForm):
    """При создании можно сразу выбрать шаблон файловой структуры (как разметку нового диска); на странице готового тома выбора нет."""

    template = forms.ModelChoiceField(
        label="Шаблон файловой структуры", required=False, queryset=VolumeTemplate.objects.all(), empty_label="Пустой том",
        help_text="Папки создаются один раз, при создании тома. Шаблоны правятся в разделе «Шаблоны файловой структуры».",
    )

    class Meta:
        model = Volume
        fields = ("slug", "name", "uuid", "label", "access")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["template"]


@admin.register(VolumeTemplate)
class VolumeTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "folders_count", "system")
    search_fields = ("name",)

    @admin.display(description="Папок")
    def folders_count(self, obj):
        return len(obj.paths())


@admin.register(Volume)
class VolumeAdmin(KeyConditionsMixin, VolumeFiles, admin.ModelAdmin):
    form = VolumeForm
    condition_fields = ("access",)
    change_form_template = "admin/filesystem/volume/change_form.html"
    inlines = (VolumeMountInline,)
    list_display = ("slug", "name", "label", "uuid", "placements_count", "mounts_count", "files_link")
    search_fields = ("slug", "name", "label", "uuid")

    def get_fieldsets(self, request, obj=None):
        fields = ["slug", "name", "uuid", "label", "access"]
        if obj is None:
            fields.append("template")
        return ((None, {"fields": fields}),)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_placements=Count("placements", distinct=True), _mounts=Count("mounts", distinct=True))

    @admin.display(description="Размещений", ordering="_placements")
    def placements_count(self, obj):
        return obj._placements

    @admin.display(description="Монтирований", ordering="_mounts")
    def mounts_count(self, obj):
        return obj._mounts

    @admin.display(description="Файлы")
    def files_link(self, obj):
        return format_html('<a href="{}">открыть</a>', reverse("admin:filesystem_volume_files", args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            filemanager.apply_template(obj, form.cleaned_data.get("template"))

    def response_add(self, request, obj, post_url_continue=None):
        response = super().response_add(request, obj, post_url_continue)
        if "_save" in request.POST and isinstance(response, HttpResponseRedirect):
            return HttpResponseRedirect(reverse("admin:filesystem_volume_files", args=[obj.pk]))      # новый том открывается файлами
        return response

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        response = super().render_change_form(request, context, add, change, form_url, obj)
        if obj is not None:
            response.context_data["files_url"] = reverse("admin:filesystem_volume_files", args=[obj.pk])
        return response


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
        ("Права", {"fields": ("owner", "group", "mode")}),
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
