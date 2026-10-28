"""Поле и виджет условий по ключам для форм админки.

Показывает тот же визуальный редактор, что и страница записи вики
(wiki/static/wiki/condition_editor.js), вместо сырого JSON, и проверяет
значение так же, как поля access/visibility вики (validate_requirements).

Подключение: примесь ConditionFieldsMixin и список полей.

    class NamespaceAdmin(ConditionFieldsMixin, admin.ModelAdmin):
        condition_fields = ("access", "visibility")
"""
import json

from django import forms
from django.db import models

from .access import validate_requirements
from .models import Key


class ConditionWidget(forms.Textarea):
    """Textarea, из которой condition_init.js делает редактор условий."""

    class Media:
        css = {"all": ("wiki/condition_editor.css",)}
        js = ("wiki/condition_editor.js", "wiki/condition_init.js")

    def __init__(self, title="", attrs=None):
        super().__init__({"rows": 3, "data-condition-editor": "1", "data-label": title, **(attrs or {})})

    def get_context(self, name, value, attrs):
        keys = list(Key.objects.order_by("slug").values("slug", "description"))
        attrs = {**(attrs or {}), "data-keys": json.dumps(keys, ensure_ascii=False)}
        return super().get_context(name, value, attrs)


class ConditionFormField(forms.JSONField):
    """JSON-поле условия.

    Пустое условие редактор отдаёт как {}. Для колонки с null=True оно
    сохраняется как NULL (так было до редактора), для обычной колонки как {}:
    None туда записать нельзя.
    """

    default_validators = [validate_requirements]

    def __init__(self, *args, empty_as_null=False, **kwargs):
        self.empty_as_null = empty_as_null
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        # None редактору нечем показать («null» он считает неверным значением)
        return "{}" if value is None else super().prepare_value(value)

    def to_python(self, value):
        result = super().to_python(value)
        if result in (None, "", {}, []):
            return None if self.empty_as_null else {}
        return result


class ConditionFieldsMixin:
    condition_fields = ()
    condition_widget = ConditionWidget          # какой виджет рисует редактор (список ключей берёт он сам)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if isinstance(db_field, models.JSONField) and db_field.name in self.condition_fields:
            kwargs["form_class"] = ConditionFormField
            kwargs["empty_as_null"] = db_field.null
            kwargs["widget"] = self.condition_widget(title=str(db_field.verbose_name).capitalize())
        return super().formfield_for_dbfield(db_field, request, **kwargs)
