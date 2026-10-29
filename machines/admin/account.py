from django.contrib import admin, messages
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from secure.access import format_condition
from secure.admin_widgets import ConditionFieldsMixin

from machines.forms import MachineProfileForm, MachineProfileTokenForm, has_real_hash
from machines.models import MachineProfile, MachineProfileToken, Session


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
        "effective_policy",
    )

    @admin.display(description="Действует")
    def effective_policy(self, obj):
        from machines import entry

        if obj.pk is None:
            return "—"
        policy = entry.policy_of(obj)
        if policy is None:
            return "Политики нет: ограничений входа нет."
        where = "профиля" if obj.entry_policy_id else "машины" if obj.machine.entry_policy_id else "типа системы"
        return f"«{policy.name}» ({where})"

    fieldsets = (
        (
            "Запись",
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
            "Адрес",
            {
                "fields": (
                    "login",
                    "mail",
                    "freq",
                ),
            },
        ),
        (
            "Пароль и ключи",
            {
                "fields": (
                    "password_state",
                    "new_password",
                    "clear_password",
                    "key_condition",
                ),
            },
        ),
        (
            "Права",
            {
                "fields": (
                    "groups",
                    "root",
                ),
            },
        ),
        (
            "Политика входа",
            {
                "fields": (
                    "entry_policy",
                    "effective_policy",
                ),
            },
        ),
        (
            "Срок подключения",
            {
                "fields": (
                    "ttl",
                    "cooldown",
                    "kick_message",
                ),
            },
        ),
    )

    inlines = (
        MachineProfileTokenInline,
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
