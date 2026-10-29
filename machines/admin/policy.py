from django.contrib import admin

from machines.models import EntryPolicy, LoginEvent


@admin.register(EntryPolicy)
class EntryPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "mode", "max_attempts", "lock_seconds", "ttl", "has_windows", "used_by")
    search_fields = ("name", "description")
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        ("Способы", {"fields": ("mode",)}),
        ("Откуда и когда", {"fields": ("sources", "via", "windows")}),
        ("Ошибки и сроки", {"fields": ("max_attempts", "attempts_window", "lock_seconds", "ttl")}),
        ("Что видит игрок", {"fields": ("denied_text", "locked_text", "window_text", "kick_text")}),
    )

    @admin.display(boolean=True, description="Окна")
    def has_windows(self, obj):
        return bool(obj.windows.strip())

    @admin.display(description="Назначена")
    def used_by(self, obj):
        return f"типов {obj.system_types.count()}, машин {obj.machines.count()}, записей {obj.profiles.count()}"


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("at", "profile", "user", "kind", "source", "detail")
    list_filter = ("kind", "profile__machine")
    search_fields = ("profile__login", "user__username", "source")
    list_select_related = ("profile__machine", "user")
    date_hierarchy = "at"

    def has_add_permission(self, request):
        return False
