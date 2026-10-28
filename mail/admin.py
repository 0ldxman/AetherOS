from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from secure.access import format_condition
from secure.admin_widgets import ConditionFieldsMixin

from .addresses import split
from .models import Attachment, ComposeProgress, ComposeTask, Delivered, Message, MessageRead, Trashed


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ("kind", "label", "path", "asset", "item", "save_path", "order")
    autocomplete_fields = ("asset", "item")


class TrashedInline(admin.TabularInline):
    """В чьих корзинах лежит письмо: персонаж «удалил» его, игрок под этим профилем найдёт."""

    model = Trashed
    extra = 0
    autocomplete_fields = ("profile",)
    verbose_name = "в корзине у профиля"
    verbose_name_plural = "В корзине у профилей"


@admin.register(Message)
class MessageAdmin(ConditionFieldsMixin, admin.ModelAdmin):
    condition_fields = ("key_condition",)
    inlines = (AttachmentInline, TrashedInline)
    date_hierarchy = "sent_at"

    list_display = (
        "subject_or_blank",
        "sender",
        "to",
        "status",
        "sent_at",
        "label",
        "trigger",
        "condition",
        "readers",
    )
    list_display_links = ("subject_or_blank",)
    list_filter = ("status", "label", "sent_at")
    search_fields = ("subject", "body", "slug", "sender", "recipients")
    ordering = ("-sent_at",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("sender", "recipients", "subject", "body", "sent_at", "status")}),
        ("Дополнительно", {"fields": ("slug", "key_condition", "label", "label_tone"), "classes": ("collapse",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_readers=Count("reads", distinct=True))

    @admin.display(description="Название", ordering="subject")
    def subject_or_blank(self, obj):
        return obj.subject or format_html("<i>{}</i>", "(без названия)")

    @admin.display(description="Кому")
    def to(self, obj):
        return ", ".join(split(obj.recipients)) or "—"

    @admin.display(description="Триггер", boolean=True, ordering="slug")
    def trigger(self, obj):
        return obj.is_trigger

    @admin.display(description="Условие по ключам")
    def condition(self, obj):
        return format_condition(obj.key_condition) or "—"

    @admin.display(description="Прочитали", ordering="_readers")
    def readers(self, obj):
        return obj._readers


@admin.register(MessageRead)
class MessageReadAdmin(admin.ModelAdmin):
    list_select_related = ("message", "user")
    list_display = ("message", "user", "session_short", "read_at")
    list_filter = ("read_at",)
    search_fields = ("message__subject", "user__username")
    readonly_fields = ("message", "user", "session_key", "read_at")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Сессия")
    def session_short(self, obj):
        return obj.session_key[:8] if obj.session_key else "—"


@admin.register(Delivered)
class DeliveredAdmin(admin.ModelAdmin):
    list_select_related = ("message", "user")
    list_display = ("message", "user", "created_at", "available_at")
    list_filter = ("available_at",)
    search_fields = ("message__subject", "message__slug", "user__username")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at",)


@admin.register(ComposeTask)
class ComposeTaskAdmin(ConditionFieldsMixin, admin.ModelAdmin):
    condition_fields = ("key_condition",)
    list_select_related = ("profile", "profile__machine")
    list_display = ("subject_or_blank", "profile", "recipients_line", "max_attempts", "reply_delay", "replies_count", "condition")
    list_display_links = ("subject_or_blank",)
    search_fields = ("subject", "recipients", "target", "profile__login", "profile__mail")
    autocomplete_fields = ("profile",)
    filter_horizontal = ("replies",)

    fieldsets = (
        ("Who writes to whom", {"fields": ("profile", "recipients", "subject")}),
        ("Text to type", {"fields": ("target",)}),
        ("Reply", {"fields": ("replies", "reply_delay")}),
        ("Rules", {"fields": ("key_condition", "max_attempts")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_replies=Count("replies", distinct=True))

    @admin.display(description="Тема", ordering="subject")
    def subject_or_blank(self, obj):
        return obj.subject or format_html("<i>{}</i>", "(без названия)")

    @admin.display(description="Кому")
    def recipients_line(self, obj):
        return ", ".join(split(obj.recipients))

    @admin.display(description="Ответов", ordering="_replies")
    def replies_count(self, obj):
        return obj._replies

    @admin.display(description="Условие по ключам")
    def condition(self, obj):
        return format_condition(obj.key_condition) or "—"


@admin.register(ComposeProgress)
class ComposeProgressAdmin(admin.ModelAdmin):
    """Что игроки сделали с задачами. Удалить запись значит сбросить прогресс игрока."""

    list_select_related = ("task", "user")
    list_display = ("task", "user", "attempts", "sent_at")
    list_filter = ("sent_at",)
    search_fields = ("task__subject", "user__username")
    readonly_fields = ("task", "user", "attempts", "sent_at", "text")

    def has_add_permission(self, request):
        return False
