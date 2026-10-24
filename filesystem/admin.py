from django.contrib import admin
from django.db.models import Count

from .forms import MachineFileForm
from .models import (
    FileKey,
    MachineFile,
    SessionFile,
)


class FileKeyInline(admin.TabularInline):
    """Ключи файла прямо на его странице."""

    model = FileKey
    extra = 0
    autocomplete_fields = ("key",)


@admin.register(MachineFile)
class MachineFileAdmin(admin.ModelAdmin):
    form = MachineFileForm
    inlines = (FileKeyInline,)
    list_select_related = ("machine",)

    list_display = (
        "path",
        "machine",
        "file_type",
        "has_state",
        "keys_count",
        "url",
        "updated_at",
    )

    list_display_links = (
        "path",
    )

    list_filter = (
        "file_type",
        "machine",
    )

    search_fields = (
        "path",
        "machine__name",
        "machine__hostname",
        "url",
    )

    autocomplete_fields = (
        "machine",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "File",
            {
                "fields": (
                    "id",
                    "machine",
                    "path",
                    "file_type",
                    "url",
                ),
            },
        ),
        (
            "State",
            {
                "fields": (
                    "state",
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    ordering = (
        "machine",
        "path",
    )

    @admin.display(
        boolean=True,
        description="State",
    )
    def has_state(self, obj):
        return bool(obj.state)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_keys=Count("keys", distinct=True))

    @admin.display(description="Ключей", ordering="_keys")
    def keys_count(self, obj):
        return obj._keys


@admin.register(SessionFile)
class SessionFileAdmin(admin.ModelAdmin):
    list_select_related = (
        "session__user",
        "session__profile__machine",
        "file__machine",
    )

    list_display = (
        "id",
        "session",
        "file",
        "path",
        "is_deleted",
        "has_state",
    )

    list_filter = (
        "session__profile__machine",
    )

    search_fields = (
        "path",
        "file__path",
        "session__user__username",
        "session__profile__name",
        "session__profile__login",
        "session__profile__machine__hostname",
    )

    autocomplete_fields = (
        "session",
        "file",
    )

    readonly_fields = (
        "id",
    )

    fieldsets = (
        (
            "Session File",
            {
                "fields": (
                    "id",
                    "session",
                    "file",
                    "path",
                    "deleted_at",
                ),
            },
        ),
        (
            "State",
            {
                "fields": (
                    "state",
                ),
            },
        ),
    )

    ordering = (
        "-id",
    )

    @admin.display(
        boolean=True,
        description="Deleted",
    )
    def is_deleted(self, obj):
        return obj.deleted_at is not None

    @admin.display(
        boolean=True,
        description="State",
    )
    def has_state(self, obj):
        return bool(obj.state)


@admin.register(FileKey)
class FileKeyAdmin(admin.ModelAdmin):
    list_select_related = ("file__machine", "key")

    list_display = (
        "id",
        "file",
        "key",
    )

    list_filter = (
        "key",
        "file__machine",
    )

    search_fields = (
        "file__path",
        "key__slug",
        "key__description",
        "file__machine__hostname",
    )

    autocomplete_fields = (
        "file",
        "key",
    )

    readonly_fields = (
        "id",
    )

    ordering = (
        "file",
        "key",
    )