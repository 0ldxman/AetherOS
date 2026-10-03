from django import forms
from django.contrib import admin
from django.contrib.auth.hashers import make_password

from .models import DesktopApp, Machine, MachineApp, MachineSession


class MachineAdminForm(forms.ModelForm):
    new_password = forms.CharField(
        required=False,
        label="Пароль",
        widget=forms.PasswordInput(render_value=False),
        help_text="Оставь пустым, чтобы не менять. В базе хранится только хеш.",
    )

    class Meta:
        model = Machine
        exclude = ["password"]


class MachineAppInline(admin.TabularInline):
    model = MachineApp
    extra = 0


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    form = MachineAdminForm
    list_display = ("name", "ip", "login", "style")
    search_fields = ("name", "ip", "login")
    filter_horizontal = ("keys", "authorized_keys")
    inlines = [MachineAppInline]

    def save_model(self, request, obj, form, change):
        raw = form.cleaned_data.get("new_password")
        if raw:
            obj.set_password(raw)
        elif not change:
            obj.password = make_password(None)  # непригодный пароль, войти нельзя
        super().save_model(request, obj, form, change)


@admin.register(DesktopApp)
class DesktopAppAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "url")


@admin.register(MachineSession)
class MachineSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "machine", "started_at", "ended_at")
    list_filter = ("machine",)