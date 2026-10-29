from django import forms
from django.contrib import admin

from machines.models import Group
from machines.access.privileges import PRIVILEGES


class GroupForm(forms.ModelForm):
    privileges = forms.MultipleChoiceField(
        label="Привилегии", required=False, choices=list(PRIVILEGES.items()), widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Group
        fields = ("name", "privileges", "everyone", "disabled")


class SystemGroupInline(admin.TabularInline):
    """Группы по умолчанию для всех машин этого типа системы."""

    model = Group
    fk_name = "system_type"
    form = GroupForm
    extra = 0
    fields = ("name", "privileges", "everyone")


class MachineGroupInline(admin.TabularInline):
    """Группы машины: одноимённая заменяет группу типа системы, отключённая прячет её."""

    model = Group
    fk_name = "machine"
    form = GroupForm
    extra = 0
    fields = ("name", "privileges", "everyone", "disabled")
