from django.contrib import admin

from .models import Document, Namespace


@admin.register(Namespace)
class NamespaceAdmin(admin.ModelAdmin):
    list_display = ("path", "parent")
    search_fields = ("name",)
    list_filter = ("parent",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "namespace", "type", "updated_at")
    list_filter = ("namespace", "type")
    search_fields = ("title",)
    readonly_fields = ("created_at", "created_by", "updated_at", "updated_by")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)