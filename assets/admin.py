from django.contrib import admin, messages
from django.template.defaultfilters import filesizeformat
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html

from assets.forms import AssetAdminForm
from assets.models import Asset
from assets.services import asset_widget_kind


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
        "slug",
        "public_id",
        "viewer_type",
        "content_type",
        "size_display",
        "wiki_snippet",
        "open_link",
        "file_id",
        "updated_at",
    )

    list_display_links = (
        "id",
        "name",
    )

    search_fields = (
        "id",
        "name",
        "slug",
        "public_id",
        "file_id",
        "filename",
    )

    list_filter = (
        "viewer_type",
    )

    readonly_fields = (
        "id",
        "public_id",
        "filename",
        "content_type",
        "size",
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
                    "slug",
                    "file_id",
                    "viewer_type",
                ),
            },
        ),
        (
            "File (cached from Nextcloud)",
            {
                "fields": (
                    "filename",
                    "content_type",
                    "size",
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

    actions = ("refresh_metadata",)

    @admin.display(description="Размер", ordering="size")
    def size_display(self, obj):
        return filesizeformat(obj.size) if obj.size else "—"

    @admin.display(description="Для вики")
    def wiki_snippet(self, obj):
        # то, что вставляется в текст записи; slug короче и читаемее UUID
        ref = obj.slug or obj.public_id
        return format_html("<code>::{} {}</code>", asset_widget_kind(obj), ref)

    @admin.display(description="Просмотр")
    def open_link(self, obj):
        try:
            url = reverse("asset_viewer:viewer", args=[obj.public_id])
        except NoReverseMatch:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">открыть</a>', url)

    def save_model(self, request, obj, form, change):
        # Метаданные обновляем при создании и при смене файла.
        if not change or "file_id" in form.changed_data:
            try:
                obj.refresh_metadata()
            except Exception as exc:
                self.message_user(
                    request,
                    f"Не удалось получить метаданные файла: {exc}",
                    level=messages.WARNING,
                )

        super().save_model(request, obj, form, change)

    @admin.action(description="Обновить метаданные файла из Nextcloud")
    def refresh_metadata(self, request, queryset):
        updated = 0
        failed = 0

        for asset in queryset:
            try:
                asset.refresh_metadata()
            except Exception:
                failed += 1
                continue

            asset.save(
                update_fields=[
                    "filename",
                    "content_type",
                    "size",
                    "updated_at",
                ]
            )
            updated += 1

        if updated:
            self.message_user(
                request,
                f"Обновлено ассетов: {updated}.",
                level=messages.SUCCESS,
            )

        if failed:
            self.message_user(
                request,
                f"Не удалось обновить: {failed}.",
                level=messages.WARNING,
            )