from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count

from users.models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ("profiles_count", "last_login")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_profiles=Count("machine_profiles", distinct=True))

    @admin.display(description="Профилей", ordering="_profiles")
    def profiles_count(self, obj):
        return obj._profiles
