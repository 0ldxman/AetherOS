from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from secure.access import format_condition
from secure.admin_widgets import ConditionFieldsMixin

from .models import Attachment, Message, MessageRead


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ("label", "path", "order")


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
        "machine",
        "sent_at",
        "condition",
        "readers",
    )
    list_display_links = ("subject_or_blank",)
    list_filter = ("machine", "sent_at")
    search_fields = ("subject", "body", "sender_name", "sender_address", "to_login")
    autocomplete_fields = ("machine",)
    ordering = ("-sent_at",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Letter", {"fields": ("sender_name", "sender_address", "to_login", "machine", "sent_at")}),
        ("Content", {"fields": ("subject", "body")}),
        ("Visibility", {"fields": ("key_condition",)}),
        ("Metadata", {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_readers=Count("reads", distinct=True))

    @admin.display(description="Тема", ordering="subject")
    def subject_or_blank(self, obj):
        return obj.subject or format_html("<i>{}</i>", "(без темы)")

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
