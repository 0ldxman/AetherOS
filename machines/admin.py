from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.db.models import Count
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html

from secure.access import format_condition
from secure.admin_widgets import ConditionFieldsMixin

from .forms import MachineProfileForm, MachineProfileTokenForm, has_real_hash
from .models import (
    Machine,
    MachineProfile,
    MachineProfileHID,
    MachineProfileToken,
    NetNode,
    NetResource,
    Session,
    MachineApp,
    VolumeMount,
)

class MachineAppInline(admin.TabularInline):
    model = MachineApp
    extra = 0
    fields = ("label", "glyph", "suffix", "path", "order")
    show_change_link = True  # условие по ключам правится на странице приложения


class VolumeMountInline(admin.TabularInline):
    model = VolumeMount
    extra = 0
    fields = ("namespace", "order")


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
        "mail",
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
        VolumeMountInline,
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
    form = MachineProfileTokenForm
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
class MachineProfileAdmin(ConditionFieldsMixin, admin.ModelAdmin):
    condition_fields = ("key_condition",)
    form = MachineProfileForm
    list_select_related = ("machine", "user")
    actions = ("hash_plain_passwords",)

    list_display = (
        "id",
        "name",
        "machine",
        "user",
        "login",
        "mail",
        "freq",
        "has_password",
        "condition",
    )

    list_filter = (
        "machine",
    )

    search_fields = (
        "name",
        "login",
        "mail",
        "machine__name",
        "machine__hostname",
    )

    autocomplete_fields = (
        "machine",
        "user",
    )

    readonly_fields = (
        "id",
        "password_state",
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
                    "mail",
                    "freq",
                ),
            },
        ),
        (
            "Authentication",
            {
                "fields": (
                    "password_state",
                    "new_password",
                    "clear_password",
                    "key_condition",
                ),
            },
        ),
    )

    inlines = (
        MachineProfileTokenInline,
        MachineProfileHIDInline,
    )

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get("new_password"):
            obj.password_hash = make_password(form.cleaned_data["new_password"])
        elif form.cleaned_data.get("clear_password"):
            obj.password_hash = ""
        super().save_model(request, obj, form, change)

    @admin.display(description="Пароль")
    def password_state(self, obj):
        if not obj.pk or not obj.password_hash:
            return "не задан"
        if has_real_hash(obj.password_hash):
            return "задан (хэш)"
        return "ВНИМАНИЕ: в поле лежит не хэш, а открытый текст. Задайте пароль заново или используйте действие «Захэшировать открытые пароли»."

    @admin.action(description="Захэшировать открытые пароли")
    def hash_plain_passwords(self, request, queryset):
        fixed = 0
        for profile in queryset.exclude(password_hash=""):
            if not has_real_hash(profile.password_hash):
                profile.password_hash = make_password(profile.password_hash)
                profile.save(update_fields=["password_hash"])
                fixed += 1
        self.message_user(request, f"Захэшировано паролей: {fixed}.", messages.SUCCESS)

    @admin.display(boolean=True, description="Password")
    def has_password(self, obj):
        return bool(obj.password_hash)

    @admin.display(description="Условие по ключам")
    def condition(self, obj):
        return format_condition(obj.key_condition) or "—"


# ==================================================
# Machine Profile Token
# ==================================================

@admin.register(MachineProfileToken)
class MachineProfileTokenAdmin(admin.ModelAdmin):
    form = MachineProfileTokenForm
    list_select_related = ("profile__machine",)
    actions = ("reset_usage",)

    list_display = (
        "token",
        "profile",
        "uses",
        "expires_at",
        "is_valid",
        "created_at",
    )

    list_display_links = (
        "token",
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

    @admin.display(description="Использовано")
    def uses(self, obj):
        return f"{obj.usage} / {obj.max_usage}" if obj.max_usage is not None else f"{obj.usage} / ∞"

    @admin.display(boolean=True, description="Действует")
    def is_valid(self, obj):
        if obj.expires_at is not None and obj.expires_at <= timezone.now():
            return False
        return obj.max_usage is None or obj.usage < obj.max_usage

    @admin.action(description="Сбросить счётчик использований")
    def reset_usage(self, request, queryset):
        count = queryset.update(usage=0)
        self.message_user(request, f"Сброшено токенов: {count}.", messages.SUCCESS)


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


# ==================================================
# Machine App
# ==================================================

@admin.register(MachineApp)
class MachineAppAdmin(ConditionFieldsMixin, admin.ModelAdmin):
    condition_fields = ("key_condition",)
    list_display = ("label", "machine", "path", "order", "condition")
    list_display_links = ("label",)
    list_filter = ("machine",)
    list_select_related = ("machine",)
    search_fields = ("label", "path", "machine__name", "machine__hostname")
    autocomplete_fields = ("machine",)
    ordering = ("machine", "order", "id")

    @admin.display(description="Условие по ключам")
    def condition(self, obj):
        return format_condition(obj.key_condition) or "—"


class NetNodeInline(admin.TabularInline):
    model = NetNode
    extra = 0
    fields = ("path", "response", "file", "token")
    raw_id_fields = ("file",)
    show_change_link = True  # условие по ключам правится на странице узла


@admin.register(NetResource)
class NetResourceAdmin(ConditionFieldsMixin, admin.ModelAdmin):
    condition_fields = ("key_condition",)
    list_display = ("address", "title", "nodes_count", "token_set", "condition")
    search_fields = ("address", "title")
    inlines = [NetNodeInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_nodes=Count("nodes"))

    @admin.display(description="Узлов", ordering="_nodes")
    def nodes_count(self, obj):
        return obj._nodes

    @admin.display(description="Токен", boolean=True)
    def token_set(self, obj):
        return bool(obj.token)

    @admin.display(description="Условие по ключам")
    def condition(self, obj):
        return format_condition(obj.key_condition) or "—"


@admin.register(NetNode)
class NetNodeAdmin(ConditionFieldsMixin, admin.ModelAdmin):
    condition_fields = ("key_condition",)
    list_display = ("__str__", "has_file", "condition")
    list_filter = ("resource",)
    search_fields = ("path", "resource__address")
    raw_id_fields = ("file",)

    @admin.display(description="Файл", boolean=True)
    def has_file(self, obj):
        return obj.file_id is not None

    @admin.display(description="Условие по ключам")
    def condition(self, obj):
        return format_condition(obj.key_condition) or "—"

