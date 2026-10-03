from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Key, User, UserKey


class UserKeyInline(admin.TabularInline):
    model = UserKey
    extra = 0


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = [UserKeyInline]


@admin.register(Key)
class KeyAdmin(admin.ModelAdmin):
    list_display = ("slug", "description")
    search_fields = ("slug", "description")