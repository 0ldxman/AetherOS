from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from secure.access import format_condition
from secure.admin_widgets import ConditionFieldsMixin

from .models import Attachment, ComposeProgress, ComposeTask, Delivered, Message, MessageRead


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ("kind", "label", "path", "asset", "machine_file", "order")
    autocomplete_fields = ("asset", "machine_file")


@admin.register(Message)
class MessageAdmin(ConditionFieldsMixin, admin.ModelAdmin):
    condition_fields = ("key_condition",)
    inlines = (AttachmentInline,)
    list_select_related = ("machine",)
    date_hierarchy = "sent_at"

    list_display = (
        "subject_or_blank",
        "sender_name",
        "to_login",
        "box",
        "machine",
        "label",
        "sent_at",
        "condition",
        "readers",
    )
    list_display_links = ("subject_or_blank",)
    list_filter = ("machine", "is_draft", "delivery", "label", "sent_at")
    search_fields = ("subject", "body", "slug", "sender_name", "sender_address", "sender_login", "to_login")
    autocomplete_fields = ("machine",)
    ordering = ("-sent_at",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Letter", {"fields": ("sender_name", "sender_address", "sender_login", "to_login", "machine", "sent_at")}),
        ("Content", {"fields": ("subject", "body", "status_note", "label", "label_tone")}),
        ("Mailbox", {"fields": ("is_draft",)}),
        ("Visibility", {"fields": ("delivery", "slug", "key_condition")}),
        ("Metadata", {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_readers=Count("reads", distinct=True))

    @admin.display(description="Тема", ordering="subject")
    def subject_or_blank(self, obj):
        return obj.subject or format_html("<i>{}</i>", "(без темы)")

    @admin.display(description="Куда")
    def box(self, obj):
        if obj.is_draft:
            return f"черновик {obj.sender_login or '?'}"
        where = f"→ {obj.to_login}" if obj.to_login else "→ всем"
        return f"{where} (триггер)" if obj.delivery == Message.Delivery.TRIGGER else where

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
    list_select_related = ("machine",)
    list_display = ("subject_or_blank", "machine", "login", "to_login", "max_attempts", "reply_delay", "replies_count", "condition")
    list_display_links = ("subject_or_blank",)
    list_filter = ("machine",)
    search_fields = ("subject", "login", "to_login", "target")
    autocomplete_fields = ("machine",)
    filter_horizontal = ("replies",)

    fieldsets = (
        ("Who writes to whom", {"fields": ("machine", "login", "to_login", "subject")}),
        ("Text to type", {"fields": ("target",)}),
        ("Reply", {"fields": ("replies", "reply_delay")}),
        ("Rules", {"fields": ("key_condition", "max_attempts")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_replies=Count("replies", distinct=True))

    @admin.display(description="Тема", ordering="subject")
    def subject_or_blank(self, obj):
        return obj.subject or format_html("<i>{}</i>", "(без темы)")

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
