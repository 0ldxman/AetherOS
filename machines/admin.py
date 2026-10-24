from django.contrib import admin
from django.contrib import messages
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Machine,
    MachineProfile,
    MachineProfileHID,
    MachineProfileToken,
    Session,
    MachineApp,
)

class MachineAppInline(admin.TabularInline):
    model = MachineApp
    extra = 0


# ==================================================
# Machine Profile
# ==================================================

class MachineProfileInline(admin.TabularInline):
    model = MachineProfile
    extra = 0

    fields = (
        "name",
        "user",
        "login",
        "freq",
    )

    show_change_link = True


# ==================================================
# Machine
# ==================================================

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
class MachineAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "hostname",
        "status",
        "system",
        "is_system",
        "profiles_count",
        "apps_count",
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
        MachineAppInline,
    )

    actions = (
        delete_selected_machines,
    )

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_system:
            return False

        return super().has_delete_permission(request, obj)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _profiles=Count("profiles", distinct=True),
            _apps=Count("machine_apps", distinct=True),
            _files=Count("files", distinct=True),
        )

    @admin.display(description="Профилей", ordering="_profiles")
    def profiles_count(self, obj):
        return obj._profiles

    @admin.display(description="Приложений", ordering="_apps")
    def apps_count(self, obj):
        return obj._apps

    @admin.display(description="Файлов", ordering="_files")
    def files_link(self, obj):
        # число ведёт в список файлов именно этой машины
        url = reverse("admin:filesystem_machinefile_changelist")
        return format_html('<a href="{}?machine__id__exact={}">{}</a>', url, obj.pk, obj._files)


# ==================================================
# Profile Token
# ==================================================

class MachineProfileTokenInline(admin.TabularInline):
    model = MachineProfileToken
    extra = 0

    fields = (
        "token",
        "max_usage",
        "usage",
        "expires_at",
        "created_at",
    )

    readonly_fields = (
        "created_at",
    )


# ==================================================
# Profile HID
# ==================================================

class MachineProfileHIDInline(admin.TabularInline):
    model = MachineProfileHID
    extra = 0

    fields = (
        "hid",
    )


# ==================================================
# Machine Profile
# ==================================================

@admin.register(MachineProfile)
class MachineProfileAdmin(admin.ModelAdmin):
    list_select_related = ("machine", "user")

    list_display = (
        "id",
        "name",
        "machine",
        "user",
        "login",
        "freq",
        "has_password",
        "has_key_condition",
    )

    list_filter = (
        "machine",
    )

    search_fields = (
        "name",
        "login",
        "machine__name",
        "machine__hostname",
    )

    autocomplete_fields = (
        "machine",
        "user",
    )

    readonly_fields = (
        "id",
    )

    fieldsets = (
        (
            "Profile",
            {
                "fields": (
                    "id",
                    "name",
                    "machine",
                    "user",
                ),
            },
        ),
        (
            "Endpoint",
            {
                "fields": (
                    "login",
                    "freq",
                ),
            },
        ),
        (
            "Authentication",
            {
                "fields": (
                    "password_hash",
                    "key_condition",
                ),
            },
        ),
    )

    inlines = (
        MachineProfileTokenInline,
        MachineProfileHIDInline,
    )

    def has_password(self, obj):
        return bool(obj.password_hash)

    has_password.boolean = True
    has_password.short_description = "Password"

    def has_key_condition(self, obj):
        return bool(obj.key_condition)

    has_key_condition.boolean = True
    has_key_condition.short_description = "Key condition"


# ==================================================
# Machine Profile Token
# ==================================================

@admin.register(MachineProfileToken)
class MachineProfileTokenAdmin(admin.ModelAdmin):
    list_select_related = ("profile__machine",)

    list_display = (
        "id",
        "profile",
        "token",
        "max_usage",
        "usage",
        "expires_at",
        "created_at",
    )

    list_filter = (
        "expires_at",
        "profile__machine",
    )

    search_fields = (
        "token",
        "profile__name",
        "profile__login",
        "profile__machine__hostname",
    )

    autocomplete_fields = (
        "profile",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "-created_at",
    )


# ==================================================
# Machine Profile HID
# ==================================================

@admin.register(MachineProfileHID)
class MachineProfileHIDAdmin(admin.ModelAdmin):
    list_select_related = ("profile__machine",)

    list_display = (
        "id",
        "profile",
        "hid",
    )

    list_filter = (
        "profile__machine",
    )

    search_fields = (
        "hid",
        "profile__name",
        "profile__login",
        "profile__machine__hostname",
    )

    autocomplete_fields = (
        "profile",
    )


# ==================================================
# Session
# ==================================================

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_select_related = ("user", "profile__machine")
    date_hierarchy = "created_at"

    list_display = (
        "id",
        "user",
        "profile",
        "machine",
        "login",
        "freq",
        "created_at",
    )

    list_filter = (
        "profile__machine",
    )

    search_fields = (
        "user__username",
        "profile__name",
        "profile__login",
        "profile__machine__hostname",
    )

    autocomplete_fields = (
        "user",
        "profile",
    )

    readonly_fields = (
        "id",
        "created_at",
    )

    ordering = (
        "-created_at",
    )

    @admin.display(description="Machine")
    def machine(self, obj):
        return obj.profile.machine

    @admin.display(description="Login")
    def login(self, obj):
        return obj.profile.login

    @admin.display(description="Freq")
    def freq(self, obj):
        return obj.profile.freq