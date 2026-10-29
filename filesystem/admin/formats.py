from django.contrib import admin

from filesystem.admin.forms import FileEncodingForm, FileFormatForm, FormatPartFormSet
from filesystem.models import FileEncoding, FileFormat, FormatPart


class FormatPartInline(admin.TabularInline):
    model = FormatPart
    formset = FormatPartFormSet
    extra = 0
    fields = ("order", "name", "source", "value")


@admin.register(FileFormat)
class FileFormatAdmin(admin.ModelAdmin):
    form = FileFormatForm
    inlines = (FormatPartInline,)
    list_display = ("name", "title", "extension", "kind", "content", "markup", "editable", "magic")
    list_filter = ("kind", "content", "markup", "editable")
    search_fields = ("name", "title", "extension")


@admin.register(FileEncoding)
class FileEncodingAdmin(admin.ModelAdmin):
    form = FileEncodingForm
    list_display = ("name", "title", "kind", "param")
    list_filter = ("kind",)
    search_fields = ("name", "title")
