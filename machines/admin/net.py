from django.contrib import admin
from django.db.models import Count

from secure.access import format_condition
from secure.admin_widgets import ConditionFieldsMixin

from machines.models import NetNode, NetResource


class NetNodeInline(admin.TabularInline):
    model = NetNode
    extra = 0
    fields = ("path", "response", "item", "token")
    autocomplete_fields = ("item",)
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
    autocomplete_fields = ("item",)

    @admin.display(description="Файл", boolean=True)
    def has_file(self, obj):
        return obj.item_id is not None

    @admin.display(description="Условие по ключам")
    def condition(self, obj):
        return format_condition(obj.key_condition) or "—"
