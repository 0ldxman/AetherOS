from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count
from django.utils.html import format_html, format_html_join

from secure.usage import key_usage

from secure.models import Key

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ("profiles_count", "last_login")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_profiles=Count("machine_profiles", distinct=True))

    @admin.display(description="Профилей", ordering="_profiles")
    def profiles_count(self, obj):
        return obj._profiles


@admin.register(Key)
class KeyAdmin(admin.ModelAdmin):
    list_display = ("slug", "description", "updated_at")
    search_fields = ("slug", "description")
    readonly_fields = ("usage",)

    @admin.display(description="Где используется")
    def usage(self, obj):
        if obj.pk is None:
            return "—"
        rows = key_usage(obj.slug)
        if not rows:
            return "Нигде: ни в вики, ни в условиях машин, ни среди ключей файлов."
        return format_html(
            "<ul>{}</ul>",
            format_html_join("", '<li>{}: <a href="{}">{}</a></li>', ((r.kind, r.url, r.label) for r in rows)),
        )
