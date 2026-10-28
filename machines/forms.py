import secrets

from django import forms
from django.contrib.auth.hashers import identify_hasher

from .models import MachineProfile, MachineProfileToken

TOKEN_BYTES = 9  # ~12 символов: удобно диктовать и вводить


def has_real_hash(value):
    """Похоже ли значение на хэш пароля Django (а не на открытый текст)."""
    try:
        identify_hasher(value)
    except ValueError:
        return False
    return True


def new_token():
    while True:
        token = secrets.token_urlsafe(TOKEN_BYTES)
        if not MachineProfileToken.objects.filter(token=token).exists():
            return token


class MachineProfileForm(forms.ModelForm):
    """Пароль задаётся отдельным полем и хранится только в виде хэша."""

    new_password = forms.CharField(
        required=False,
        label="Новый пароль",
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Пустое поле: пароль не меняется. Сохраняется только хэш.",
    )
    clear_password = forms.BooleanField(
        required=False,
        label="Убрать пароль",
        help_text="Вход на профиль станет без пароля.",
    )

    groups = forms.CharField(
        required=False, label="Группы",
        help_text="Имена групп через запятую. Группы «все записи» входят сами; привилегии складываются по группам.",
    )

    class Meta:
        model = MachineProfile
        exclude = ("password_hash",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["groups"] = ", ".join(self.instance.groups or [])

    def clean_groups(self):
        return [name.strip() for name in self.cleaned_data.get("groups", "").split(",") if name.strip()]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") and cleaned.get("clear_password"):
            raise forms.ValidationError("Нельзя одновременно задать новый пароль и убрать пароль.")
        return cleaned


class MachineProfileTokenForm(forms.ModelForm):
    """Пустой токен означает «сгенерировать»."""

    token = forms.CharField(
        required=False,
        max_length=255,
        help_text="Оставьте пустым: токен сгенерируется.",
    )

    class Meta:
        model = MachineProfileToken
        fields = "__all__"

    def clean_token(self):
        return self.cleaned_data["token"].strip() or new_token()
