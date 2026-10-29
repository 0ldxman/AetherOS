from django.contrib import admin

from machines.admin.groups import SystemGroupInline
from machines.models import Machine, Place, SystemType


class SystemPlaceInline(admin.TabularInline):
    model = Place
    fk_name = "system_type"
    extra = 0
    fields = ("name", "path")


@admin.register(SystemType)
class SystemTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "path_style", "machines_count")
    search_fields = ("code", "name")
    inlines = (SystemPlaceInline, SystemGroupInline)

    @admin.display(description="Машин")
    def machines_count(self, obj):
        return Machine.objects.filter(system=obj.code).count()
