from django.contrib import admin

from .models import Country, Ownership, Province


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "valid_from", "valid_to", "predecessor")
    search_fields = ("name", "code")
    list_filter = ("valid_from",)
    autocomplete_fields = ("predecessor",)


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "source_code")
    search_fields = ("name", "code", "source_code")


@admin.register(Ownership)
class OwnershipAdmin(admin.ModelAdmin):
    list_display = ("province", "country", "date_from", "de_jure", "de_facto")
    list_filter = ("de_jure", "de_facto", "country")
    search_fields = ("province__name", "province__code", "country__name", "country__code")
    autocomplete_fields = ("province", "country")
    date_hierarchy = "date_from"