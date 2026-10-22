
from django.contrib import admin

from .forms import AssetAdminForm
from .models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    form = AssetAdminForm

    add_form_template = (
        "admin/assets/asset/change_form.html"
    )

    change_form_template = (
        "admin/assets/asset/change_form.html"
    )

    list_display = (
        "id",
        "name",
        "public_id",
        "viewer_type",
        "file_id",
        "created_at",
        "updated_at",
    )

    list_display_links = (
        "id",
        "name",
    )

    search_fields = (
        "id",
        "name",
        "public_id",
        "file_id",
    )

    list_filter = (
        "viewer_type",
    )

    readonly_fields = (
        "id",
        "public_id",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "public_id",
                    "name",
                    "file_id",
                    "viewer_type",
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
