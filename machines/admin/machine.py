from django import forms
from django.contrib import admin, messages
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html

from filesystem.admin.files import MachineFiles

from machines.admin.groups import MachineGroupInline
from machines.models import Export, Machine, MachineMount, MachineProfile, Place, SystemType


class ExportInline(admin.TabularInline):
    """Пути, которые машина отдаёт по сети."""

    model = Export
    extra = 0
    fields = ("path",)


class MachineMountInline(admin.TabularInline):
    """Тома, смонтированные на машину (docs/storage-spec.md)."""

    model = MachineMount
    fk_name = "machine"
    extra = 0
    fields = ("mode", "volume", "volume_path", "host", "host_path", "account", "mount_path", "order")
    autocomplete_fields = ("volume", "host")
    raw_id_fields = ("account",)


class MachinePlaceInline(admin.TabularInline):
    """Места этой машины, переопределяющие значения её типа системы (secrets, desktop, trash...)."""

    model = Place
    fk_name = "machine"
    extra = 0
    fields = ("name", "path")


class MachineProfileInline(admin.TabularInline):
    model = MachineProfile
    extra = 0

    fields = (
        "name",
        "user",
        "login",
        "mail",
        "freq",
    )

    show_change_link = True


@admin.action(description="Delete selected machines")
def delete_selected_machines(modeladmin, request, queryset):
    protected = queryset.filter(is_system=True)
    deletable = queryset.filter(is_system=False)

    protected_count = protected.count()

    if protected_count:
        modeladmin.message_user(
            request,
            f"{protected_count} system machine(s) cannot be deleted.",
            level=messages.ERROR,
        )

    if deletable.exists():
        count = deletable.count()
        deletable.delete()

        modeladmin.message_user(
            request,
            f"{count} machine(s) deleted.",
            level=messages.SUCCESS,
        )


@admin.register(Machine)
class MachineAdmin(MachineFiles, admin.ModelAdmin):
    list_display = (
        "name",
        "hostname",
        "status",
        "system",
        "is_system",
        "profiles_count",
        "files_link",
        "hid",
        "updated_at",
    )

    list_display_links = (
        "name",
    )

    list_filter = (
        "system",
        "status",
        "is_system",
    )

    search_fields = (
        "name",
        "hostname",
        "hid",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "name",
    )

    inlines = (
        MachineProfileInline,
        MachineMountInline,
        ExportInline,
        MachinePlaceInline,
        MachineGroupInline,
    )

    actions = (
        delete_selected_machines,
    )

    change_form_template = "admin/machines/machine/change_form.html"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "system":
            choices = [(row.code, f"{row.name} ({row.code})") for row in SystemType.objects.order_by("code")]
            return forms.ChoiceField(label="Тип системы", choices=choices, initial="AETHER", help_text=db_field.help_text)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        response = super().render_change_form(request, context, add, change, form_url, obj)
        if obj is not None:
            response.context_data["files_url"] = reverse("admin:machines_machine_files", args=[obj.pk])
        return response

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_system:
            return False

        return super().has_delete_permission(request, obj)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _profiles=Count("profiles", distinct=True),
        )

    @admin.display(description="Профилей", ordering="_profiles")
    def profiles_count(self, obj):
        return obj._profiles

    @admin.display(description="Файлы")
    def files_link(self, obj):
        return format_html('<a href="{}">открыть</a>', reverse("admin:machines_machine_files", args=[obj.pk]))
