from django.contrib import admin

from .models import (
    FileKey,
    MachineFile,
    SessionFile,
)


@admin.register(MachineFile)
class MachineFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "machine",
        "path",
        "file_type",
        "ext",
        "has_state",
        "asset",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "file_type",
        "machine",
    )

    search_fields = (
        "path",
        "ext",
        "machine__name",
        "machine__hostname",
        "asset__name",
    )

    autocomplete_fields = (
        "machine",
        "asset",
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
                    "ext",
                    "asset",
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


@admin.register(SessionFile)
class SessionFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "file",
        "has_state",
    )

    list_filter = (
        "session__profile__machine",
    )

    search_fields = (
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
        description="State",
    )
    def has_state(self, obj):
        return bool(obj.state)


@admin.register(FileKey)
class FileKeyAdmin(admin.ModelAdmin):
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