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
        "file_id",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "name",
                    "file_id",
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